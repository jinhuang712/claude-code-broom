"""What stops a commit and how it gets through: fixing, accepting with a reason, and git's own pre-commit hook."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

from support import BroomCase, py_function

from broom import githook
from broom.gate import key_of


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
        self.assertIn(githook.LINE, out.stdout)
        self.assertEqual(hook.read_text(), "#!/bin/sh\nexit 0\n")

    def test_the_line_for_another_tools_hook_checks_the_commit_and_lets_that_hook_go_on(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        hook = r / ".git/hooks/pre-commit"
        theirs = f"#!/bin/sh\n{githook.LINE}\necho theirs ran >&2\n"
        hook.write_text(theirs)
        hook.chmod(0o755)
        self.assertTrue(githook.installed(r), "the line is how broom knows it is there")
        out = self.cli(r, "install-hook")
        self.assertEqual((out.returncode, hook.read_text()), (0, theirs), "their hook is never written over")
        self.assertIn("holds broom's line already", out.stdout)
        (r / "a.py").write_text(py_function("huge", 120))
        self.sh(r, "git", "add", "a.py")
        out = self.git_commit(r)
        self.assertEqual(out.returncode, 1, "no marketplace copy here: the line finds this install")
        self.assertIn("huge is 120 code lines long", out.stderr)
        self.assertNotIn("theirs ran", out.stderr)
        (r / "a.py").write_text(py_function("small", 20))
        self.sh(r, "git", "add", "a.py")
        out = self.git_commit(r)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("theirs ran", out.stderr, "a clean commit goes on to the rest of their hook")

    def test_the_line_lets_a_commit_through_where_no_broom_is_found(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        hook = r / ".git/hooks/pre-commit"
        gone = githook.LINE.replace(str(githook.PLUGIN_ROOT), "/nowhere")
        hook.write_text(f"#!/bin/sh\n{gone}\n")
        hook.chmod(0o755)
        (r / "a.py").write_text(py_function("huge", 120))
        self.sh(r, "git", "add", "a.py")
        out = self.git_commit(r)
        self.assertEqual(out.returncode, 0, "a missing broom never blocks: " + out.stderr)

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
        self.assertIn("huge is 120 code lines long", out.stderr)
        (r / "a.py").write_text(py_function("small", 20))
        self.sh(r, "git", "add", "a.py")
        out = self.git_commit(r)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_with_gits_hook_installed_the_check_is_gits_and_sees_what_the_commit_really_takes(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.assertIn("huge is 120 code lines long", self.denied(self.commit(r, "git add a.py && git commit -m x")),
                      "without git's hook, the command is read and the files it will stage are guessed")
        self.install(r)
        self.assertEqual(self.commit(r, "git add a.py && git commit -m x"), {}, "the hook no longer guesses")
        self.sh(r, "git", "add", "a.py")
        out = self.git_commit(r)
        self.assertEqual(out.returncode, 1, "git's hook, on the staged files, is what stops it")
        self.assertIn("huge is 120 code lines long", out.stderr)

    def test_content_that_passed_isnt_checked_again(self) -> None:
        quiet = '{"smells_off": ["dead_code"]'
        r = self.repo({"a.py": "x = 1\n", ".broom.json": quiet + "}"})
        (r / "a.py").write_text("".join(f"x{i} = {i}\n" for i in range(30)))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {}, "passes, and the content is recorded")
        self.assertEqual(self.cli(r, "hook", "pre-commit").returncode, 0, "git's hook: passed already")
        self.hook("edit", {"session_id": "s9", "cwd": str(r), "tool_name": "Edit",
                           "tool_input": {"file_path": str(r / "a.py")}})
        self.assertEqual(self.hook("stop", {"session_id": "s9", "cwd": str(r)}), {}, "the turn's end too")
        (r / ".broom.json").write_text(quiet + ', "limits": {"file_lines": [5, 10]}}')  # it would block now
        self.assertEqual(self.cli(r, "hook", "pre-commit").returncode, 1, "a changed .broom.json is a new bar")
        (r / ".broom.json").write_text(quiet + "}")
        self.assertEqual(self.cli(r, "hook", "pre-commit").returncode, 0, "the same bar again: passed already")

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

    OLD_FILE = "".join(f"x{i} = {i}\n" for i in range(40))  # old, with the lines an untested-file note asks for

    def hinted_commit(self, checkout: Path, how: str, git: tuple = ("git",)) -> str:
        """What git's hook says of a commit in `checkout` that adds a 60-line function to the old file pkg/sub/old.py,
        made as `how` says: `staged`, `all` (`git commit -a`) or `path` (`git commit pkg/sub/old.py`), the last two with
        the temporary index git then hands the hook. The function is a hint, which stops the commit: the denial is
        what comes back, with the checkout's path in it made `<repo>`. Each gets a data directory of its own, so a
        note one was shown isn't held back from the next."""
        env = {**self.env, "CLAUDE_PLUGIN_DATA": str(self.tmp / f"data-{uuid.uuid4().hex[:6]}")}
        old = checkout / "pkg/sub/old.py"
        old.write_text(old.read_text() + "\n\n" + py_function("grown", 60))
        if how == "staged":
            self.sh(checkout, *git, "add", "pkg/sub/old.py")
        extra = {"staged": [], "all": ["-a"], "path": ["pkg/sub/old.py"]}[how]
        out = subprocess.run([*git, "commit", "-q", "-m", "x", *extra], cwd=checkout, env=env, capture_output=True,
                             text=True)
        self.assertEqual(out.returncode, 1, out.stderr)
        return out.stderr.replace(str(checkout), "<repo>")

    @staticmethod
    def smell_lines(stderr: str) -> list:
        """The hook's lines without its notes on skipped tools (`broom skipped:` in the context, `Skipped:` in a
        denial, and the blank line before it): jscpd takes a work tree with no `.git` for no repo and says so, which is
        its own limit, not git's."""
        rows = [row for row in stderr.splitlines() if not row.startswith(("broom skipped:", "Skipped:"))]
        return rows[:-1] if rows and rows[-1] == "" else rows

    def test_git_pre_commit_reads_a_commit_in_a_linked_worktree_as_it_does_in_the_main_checkout(self) -> None:
        for how in ("staged", "all", "path"):
            r = self.repo({"pkg/sub/old.py": self.OLD_FILE})
            self.install(r)  # the hook is in the common git directory: every worktree runs it
            linked = self.tmp / f"linked-{how}"
            self.sh(r, "git", "worktree", "add", "-q", str(linked), "-b", f"side-{how}")
            in_main, in_linked = self.hinted_commit(r, how), self.hinted_commit(linked, how)
            self.assertIn("pkg/sub/old.py:", in_main, f"{how}: the hint names the file by its path in the repo")
            self.assertIn("grown is 60 code lines long", in_main, how)
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
        self.assertIn("grown is 60 code lines long", in_plain)
        self.assertEqual(self.smell_lines(in_work), self.smell_lines(in_plain))

    def accepted_repo(self) -> Path:
        """A repo whose one known issue is a 120-line function, accepted at the commit it blocked."""
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.sh(r, "git", "add", "a.py")
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.cli(r, "known", "--accept", "legacy code").returncode, 0)
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        return r

    def test_known_marks_an_issue_whose_code_changed_and_drops_none(self) -> None:
        r = self.accepted_repo()
        first = self.cli(r, "known").stdout
        self.assertIn("1 known issue(s), not raised again:", first)
        self.assertNotIn("no longer matches", first)
        (r / "a.py").write_text(py_function("huge", 120).replace("def huge", "def renamed"))
        out = self.cli(r, "known").stdout
        self.assertIn("1 known issue(s), 1 of them with their code changed, not raised again:", out)
        self.assertIn("(its code changed: no longer matches)", out)
        (r / "a.py").write_text("\n" + py_function("huge", 120))
        self.assertNotIn("no longer matches", self.cli(r, "known").stdout, "a line that moved still matches")
        (r / "a.py").write_text("x = 1\n")
        again = self.cli(r, "known").stdout
        self.assertIn("no longer matches", again)
        self.assertIn("1 known issue(s)", again, "nothing was dropped")

    def test_an_entry_of_a_deleted_worktree_names_the_main_checkouts_file_once_proven(self) -> None:
        text = py_function("huge", 120)
        r = self.repo({"a.py": text})
        gone = r / "wt-side" / "a.py"  # a worktree inside the repo, deleted since
        msg, line = "huge is 120 code lines long (over 50)", text.splitlines()[0].strip()
        old = {"file": str(gone), "line": 1, "tool": "smells", "rule": "function_lines", "msg": msg, "t": 1}
        lost = {**old, "msg": "kept is 120 code lines long (over 50)"}
        data = {key_of(gone, "smells", "function_lines", msg, line): old,  # keyed on the worktree's path, as before 0.28.1
                key_of(gone, "smells", "function_lines", lost["msg"], "def kept(x):"): lost}  # no line here proves it
        (self.tmp / "data").mkdir(exist_ok=True)
        (self.tmp / "data" / "baseline.json").write_text(json.dumps(data))
        out = self.cli(r, "known").stdout
        self.assertIn("2 known issue(s), 1 of them with their code changed", out)
        self.assertIn(f"{r / 'a.py'}:1  smells function_lines  {msg}", out)
        self.assertIn(f"wt-side/a.py:1  smells function_lines  {lost['msg']}", out)
        stored = json.loads((self.tmp / "data" / "baseline.json").read_text())
        self.assertIn(key_of(r / "a.py", "smells", "function_lines", msg, line), stored, "the key the main checkout gives")
        (r / "a.py").write_text(text + "\n")
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "", "so it is known there")

    def test_known_looks_for_the_line_in_a_linked_worktree_too(self) -> None:
        r = self.accepted_repo()
        self.sh(r, "git", "commit", "-qam", "land")
        linked = self.tmp / "side"
        self.sh(r, "git", "worktree", "add", "-q", str(linked), "-b", "side")
        (r / "a.py").write_text("x = 1\n")  # the main checkout has changed the code, the worktree still has it
        self.assertNotIn("no longer matches", self.cli(r, "known").stdout)
        (linked / "a.py").write_text("x = 1\n")
        self.assertIn("no longer matches", self.cli(r, "known").stdout)
