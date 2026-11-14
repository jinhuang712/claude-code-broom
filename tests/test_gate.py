"""What stops a commit and how it gets through: fixing, retrying, accepting, and git's own pre-commit hook."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from support import BroomCase, py_function


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
