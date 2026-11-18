"""What stops a commit and how it gets through: fixing, accepting with a reason, and git's own pre-commit hook."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from support import BroomCase, py_function

from broom import githook


class GateTest(BroomCase):
    def setUp(self) -> None:
        super().setUp()
        # The broom of the Claude Code session running the tests must not stand in for the one under test.
        dirs = self.env["PATH"].split(os.pathsep)
        self.env["PATH"] = os.pathsep.join(p for p in dirs if not (Path(p) / "broom").exists())

    def install(self, r: Path) -> None:
        out = self.cli(r, "install-hook")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def git_commit(self, r: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "commit", "-qm", "x"], cwd=r, env=self.env, capture_output=True, text=True)

    def test_install_hook_adds_git_pre_commit_and_leaves_others_alone(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.install(r)
        hook = r / ".git/hooks/pre-commit"
        self.assertTrue(os.access(hook, os.X_OK))
        self.install(r)  # its own hook it replaces
        hook.write_text("#!/bin/sh\nexit 0\n")
        out = self.cli(r, "install-hook")
        self.assertEqual(out.returncode, 1)
        self.assertIn("hook pre-commit || exit 1", out.stdout)
        self.assertEqual(hook.read_text(), "#!/bin/sh\nexit 0\n")

    def test_git_pre_commit_checks_commits_claude_code_doesnt_see(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.install(r)
        # The marketplace's copy comes first; one from before git's hook is passed over for this install.
        old = Path(self.env["CLAUDE_CONFIG_DIR"]) / "plugins/marketplaces/claude-code-broom/bin/broom"
        old.parent.mkdir(parents=True)
        old.write_text("#!/bin/sh\necho 'invalid choice' >&2\nexit 2\n")
        old.chmod(0o755)
        (r / "a.py").write_text(py_function("huge", 120))
        self.sh(r, "git", "add", "a.py")
        out = self.git_commit(r)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("huge is 120 lines long", out.stderr)
        (r / "a.py").write_text(py_function("small", 20))
        self.sh(r, "git", "add", "a.py")
        out = self.git_commit(r)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_with_gits_hook_installed_the_check_is_gits_and_sees_what_the_commit_really_takes(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.assertIn("huge is 120 lines long", self.denied(self.commit(r, "git add a.py && git commit -m x")),
                      "without git's hook, the command is read and the files it will stage are guessed")
        self.install(r)
        self.assertEqual(self.commit(r, "git add a.py && git commit -m x"), {}, "the hook no longer guesses")
        self.sh(r, "git", "add", "a.py")
        out = self.git_commit(r)
        self.assertEqual(out.returncode, 1, "git's hook, on the staged files, is what stops it")
        self.assertIn("huge is 120 lines long", out.stderr)

    def test_content_that_passed_isnt_checked_again(self) -> None:
        quiet = '{"smells_off": ["dead_code"]'
        r = self.repo({"a.py": "x = 1\n", ".broom.json": quiet + "}"})
        (r / "a.py").write_text("".join(f"x{i} = {i}\n" for i in range(30)))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {}, "passes, and the content is recorded")
        (r / ".broom.json").write_text(quiet + ', "limits": {"file_lines": [5, 10]}}')  # it would block now
        self.assertEqual(self.cli(r, "hook", "pre-commit").returncode, 0, "git's hook: passed already")
        self.hook("edit", {"session_id": "s9", "cwd": str(r), "tool_name": "Edit",
                           "tool_input": {"file_path": str(r / "a.py")}})
        self.assertEqual(self.hook("stop", {"session_id": "s9", "cwd": str(r)}), {}, "the turn's end too")
        (r / "a.py").write_text("".join(f"x{i} = {i}\n" for i in range(31)))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.cli(r, "hook", "pre-commit").returncode, 1, "new content is checked")

    def test_accepting_can_be_turned_off(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.sh(r, "git", "add", "a.py")
        self.env["BROOM_NO_ACCEPT"] = "1"
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("accepting them is off here", reason)
        self.assertNotIn("broom known --accept", reason, "Claude isn't told to do what it can't")
        out = self.cli(r, "known", "--accept", "legacy code")
        self.assertEqual(out.returncode, 1)
        self.assertIn("BROOM_NO_ACCEPT is set", out.stderr)
        self.env["BROOM_NO_ACCEPT"] = "0"
        self.assertIn("accepted", self.cli(r, "known", "--accept", "legacy code").stdout, "0 leaves it on")

    # git's hook where git names the work tree its own way: a linked worktree (GIT_DIR alone), `--work-tree` (GIT_WORK_TREE)

    OLD_FILE = "".join(f"x{i} = {i}\n" for i in range(40))  # old, with the lines an untested-file hint asks for

    def hinted_commit(self, checkout: Path, how: str, git: tuple = ("git",)) -> str:
        """What git's hook says of a commit in `checkout` that adds a 60-line function to the old file pkg/sub/old.py,
        made as `how` says: `staged`, `all` (`git commit -a`) or `path` (`git commit pkg/sub/old.py`), the last two with
        the temporary index git then hands the hook. Each gets a data directory of its own, so a note one was shown
        isn't held back from the next."""
        env = {**self.env, "CLAUDE_PLUGIN_DATA": str(self.tmp / f"data-{uuid.uuid4().hex[:6]}")}
        old = checkout / "pkg/sub/old.py"
        old.write_text(old.read_text() + "\n\n" + py_function("grown", 60))
        if how == "staged":
            self.sh(checkout, *git, "add", "pkg/sub/old.py")
        extra = {"staged": [], "all": ["-a"], "path": ["pkg/sub/old.py"]}[how]
        out = subprocess.run([*git, "commit", "-q", "-m", "x", *extra], cwd=checkout, env=env, capture_output=True,
                             text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stderr

    @staticmethod
    def smell_lines(stderr: str) -> list:
        """The hook's lines without its notes on skipped tools: jscpd takes a work tree with no `.git` for no repo and
        says so, which is its own limit, not git's."""
        return [row for row in stderr.splitlines() if not row.startswith("broom skipped:")]

    def test_git_pre_commit_reads_a_commit_in_a_linked_worktree_as_it_does_in_the_main_checkout(self) -> None:
        for how in ("staged", "all", "path"):
            r = self.repo({"pkg/sub/old.py": self.OLD_FILE})
            self.install(r)  # the hook is in the common git directory: every worktree runs it
            linked = self.tmp / f"linked-{how}"
            self.sh(r, "git", "worktree", "add", "-q", str(linked), "-b", f"side-{how}")
            in_main, in_linked = self.hinted_commit(r, how), self.hinted_commit(linked, how)
            self.assertIn("pkg/sub/old.py:", in_main, f"{how}: the hint names the file by its path in the repo")
            self.assertIn("grown is 60 lines long", in_main, how)
            self.assertNotIn("new code file", in_linked, f"{how}: the file is old")
            self.assertEqual(in_linked, in_main, f"{how}: a linked worktree gets what the main checkout gets")

    def test_git_pre_commit_reads_a_repo_used_through_git_dir_and_work_tree_as_it_does_any_repo(self) -> None:
        store, work = self.tmp / "store.git", self.tmp / "work"
        (work / "pkg/sub").mkdir(parents=True)
        (work / "pkg/sub/old.py").write_text(self.OLD_FILE)
        git = ("git", f"--git-dir={store}", f"--work-tree={work}")
        self.sh(self.tmp, "git", "init", "-q", "--bare", str(store))
        self.sh(work, *git, "add", "-A")
        self.sh(work, *git, "commit", "-qm", "init")
        hook = store / "hooks/pre-commit"  # no `.git` marks the work tree: git's variables are all there is
        hook.write_text(githook.script())
        hook.chmod(0o755)
        plain = self.repo({"pkg/sub/old.py": self.OLD_FILE})
        self.install(plain)
        in_plain = self.hinted_commit(plain, "staged")
        in_work = self.hinted_commit(work, "staged", git)
        self.assertIn("grown is 60 lines long", in_plain)
        self.assertEqual(self.smell_lines(in_work), self.smell_lines(in_plain))
