"""F2.13, a turn that changed code shows that tests ran: broom notes a Bash command that is a test run when it starts, and
a failed one when Claude Code says so; a turn's end that changed code with no test run after it, or whose last test run
failed, is told like any finding. broom never runs a test."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

from support import ROOT, BroomCase
from test_nowave import NoWaveCase
from test_testcmd import NO_RUNNERS

from broom import ledger

TEST_FILE_TEXT = "def test_a():\n    assert True\n"
NOT_RUN_TEXT = "no test ran after the last change to code"
NOT_RUN_LINE = f"a.py  tests_not_run  {NOT_RUN_TEXT}"
GIVE_UP = ("broom GAVE UP after 3 blocks: 1 finding(s) left unfixed and unaccepted: a.py tests_not_run; broom let 1 "
           "through this turn: 1 tests_not_run (gave-up)")


class TestRunCase(NoWaveCase):
    def code_repo(self, **files: str) -> Path:
        """A repo with code and a tracked test file, and the other `files` by name."""
        return self.repo({"a.py": "x = 1\n", "tests/test_a.py": TEST_FILE_TEXT, **files})

    def change(self, r: Path, text: str = "x = 2\n", name: str = "a.py") -> None:
        """Write `text` to `name`, and tell broom the turn edited it."""
        (r / name).write_text(text)
        self.hook("edit", {"session_id": "s1", "cwd": str(r), "tool_name": "Edit",
                           "tool_input": {"file_path": str(r / name)}})

    def bash(self, r: Path, command: str) -> dict:
        """The PreToolUse hook for a Bash command."""
        return self.commit(r, command)

    def failed(self, r: Path, command: str, error: str = "Exit code 1\nFAILED") -> dict:
        """The PostToolUseFailure hook for a Bash command that exited non-zero."""
        return self.hook("test-failed", {"session_id": "s1", "cwd": str(r), "hook_event_name": "PostToolUseFailure",
                                         "tool_name": "Bash", "tool_input": {"command": command}, "error": error,
                                         "is_interrupt": False, "tool_use_id": uuid.uuid4().hex})

    def runs(self) -> list:
        """The test runs noted for session s1's turn."""
        return list(ledger.read(Path(self.env["CLAUDE_PLUGIN_DATA"]) / "sessions" / "s1" / ledger.RUNS))

    def new_turn(self, r: Path) -> None:
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})

    def ledger_rows(self, event: str) -> list:
        return [x for x in ledger.every_row() if x["event"] == event]


class NotedTest(TestRunCase):
    def test_a_test_command_is_noted_when_it_starts_and_says_nothing(self) -> None:
        r = self.code_repo()
        self.assertEqual(self.bash(r, "cd . && pytest -q"), {})
        (row,) = self.runs()
        self.assertEqual(row["cmd"], "cd . && pytest -q")
        self.assertNotIn("exit", row)

    def test_a_command_that_is_no_test_run_is_not_noted(self) -> None:
        r = self.code_repo()
        for command in NO_RUNNERS + ("git status",):
            self.assertEqual(self.bash(r, command).get("hookSpecificOutput", {}).get("permissionDecision"), None)
        self.assertEqual(self.runs(), [])

    def test_a_failed_test_command_is_noted_with_its_exit_code(self) -> None:
        r = self.code_repo()
        self.assertEqual(self.failed(r, "pytest -q", "Exit code 2\nFAILED a"), {})
        (row,) = self.runs()
        self.assertEqual((row["cmd"], row["exit"]), ("pytest -q", "Exit code 2"))

    def test_the_failure_hook_exits_0_and_says_nothing_for_a_command_that_is_no_test_run(self) -> None:
        r = self.code_repo()
        self.assertEqual(self.failed(r, "ls /nonexistent", "Exit code 2"), {})
        self.assertEqual(self.failed(r, "git commit -m 'run pytest'", "Exit code 1"), {})
        self.assertEqual(self.runs(), [])
        for text in ("", "not json", "[1]"):
            out = subprocess.run([str(ROOT / "bin" / "broom"), "hook", "test-failed"], input=text, cwd=r,
                                 env=self.env, capture_output=True, text=True)
            self.assertEqual((out.returncode, out.stdout, out.stderr), (0, "", ""), text)

    def test_nothing_is_noted_where_the_turns_end_is_not_checked(self) -> None:
        for check_on in ("commit", "off"):
            r = self.code_repo(**{".broom.json": json.dumps({"check_on": check_on})})
            self.bash(r, "pytest")
            self.failed(r, "pytest")
            self.assertEqual(self.runs(), [], check_on)

    def test_a_test_command_after_a_commit_is_noted_unless_the_commit_is_denied(self) -> None:
        r = self.code_repo()
        (r / "a.py").write_text("def f(a, b, c, d, e, f):\n    return a + b + c + d + e + f\n")
        self.sh(r, "git", "add", "a.py")
        self.assertIn("params", self.denied(self.bash(r, "git commit -m x && pytest")))
        self.assertEqual(self.runs(), [], "the command was denied: it never ran")
        (r / "a.py").write_text("x = 3\n")
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.denied(self.bash(r, "git commit -m x && pytest")), "")
        self.assertEqual(len(self.runs()), 1)

    def test_the_scripts_note_a_test_run_and_its_failure_as_claude_code_runs_them(self) -> None:
        r = self.code_repo()
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Bash", "tool_input": {"command": "npm test"},
                   "tool_use_id": "toolu_01"}
        for script, more in (("commit.sh", {}), ("failed.sh", {"error": "Exit code 7\nboom"})):
            out = subprocess.run([str(ROOT / "hooks" / script)], input=json.dumps({**payload, **more}, separators=(",", ":")),
                                 capture_output=True, text=True, env=self.env, cwd=r)
            self.assertEqual((out.returncode, out.stdout, out.stderr), (0, "", ""), script)
        self.assertEqual([(x["cmd"], x.get("exit")) for x in self.runs()], [("npm test", None), ("npm test", "Exit code 7")])

    def test_a_test_command_loads_no_commit_check_and_a_commit_does(self) -> None:
        r = self.code_repo()
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Bash", "tool_input": {"command": "pytest"}}
        _, loaded = self.counted("commit", payload, r)
        self.assertNotIn("broom.commitgate", loaded)
        payload["tool_input"]["command"] = "git commit -m x"
        _, loaded = self.counted("commit", payload, r)
        self.assertIn("broom.commitgate", loaded)


class PrefilterTest(TestRunCase):
    """hooks/commit.sh and hooks/failed.sh leave before Python starts for a command that can't be a test run. The
    scripts run with a PATH that has no python3: a call that reaches Python fails with 127."""

    def reaches_python(self, script: str, repo: Path, command: str, separators: tuple = (",", ":")) -> bool:
        bins = self.tmp / "nopython"
        bins.mkdir(exist_ok=True)
        if not (bins / "cat").exists():
            (bins / "cat").symlink_to(shutil.which("cat"))
        payload = {"session_id": "s1", "transcript_path": f"{self.tmp}/test-project/t.jsonl", "cwd": str(repo),
                   "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
                   "tool_use_id": "toolu_01"}  # in the order Claude Code writes it, and as compact as it does
        r = subprocess.run([str(ROOT / "hooks" / script)], input=json.dumps(payload, separators=separators),
                           capture_output=True, text=True, env={**self.env, "PATH": str(bins)}, cwd=repo)
        self.assertIn(r.returncode, (0, 127), r.stderr)
        return r.returncode == 127

    def test_a_call_reaches_python_when_it_may_commit_or_run_tests_and_not_otherwise(self) -> None:
        r = self.code_repo()
        for script in ("commit.sh", "failed.sh"):
            for command in ("npm test", "pytest -q", "go test ./...", "make test", "python3 tests/run.py", "jest",
                            "tox", "nox -s x", "mocha", "vitest run", "ls tests/"):
                self.assertTrue(self.reaches_python(script, r, command), f"{script}: {command}")
            for command in ("ls -la", "echo hello", "git status", "cat README.md", "rg foo src"):
                self.assertFalse(self.reaches_python(script, r, command), f"{script}: {command}")
        self.assertTrue(self.reaches_python("commit.sh", r, "git commit -m x"))
        self.assertFalse(self.reaches_python("failed.sh", r, "git commit -m x"), "a failed commit is no test run")

    def test_json_with_spaces_is_read_too(self) -> None:
        r = self.code_repo()
        for command, reaches in (("ls -la", False), ("pytest", True)):
            self.assertEqual(self.reaches_python("commit.sh", r, command, (", ", ": ")), reaches, command)

    def test_a_path_with_test_in_it_makes_no_call_reach_python(self) -> None:
        r = self.tmp / "test-project"
        r.mkdir()
        self.sh(r, "git", "init", "-q")
        self.assertFalse(self.reaches_python("commit.sh", r, "ls -la"))

    def test_a_repo_that_names_test_commands_lets_every_call_through_to_python(self) -> None:
        r = self.code_repo(**{".broom.json": '{\n  // mine\n  "test_commands": ["just check"]\n}'})
        self.assertTrue(self.reaches_python("commit.sh", r, "just check"))
        self.assertTrue(self.reaches_python("failed.sh", r, "just check"))
        sub = r / "sub"
        sub.mkdir()
        self.assertTrue(self.reaches_python("commit.sh", sub, "echo hi"), "from a folder of the repo too")

    def test_a_linked_worktree_without_its_own_config_reads_the_main_worktrees(self) -> None:
        r = BroomCase.repo(self, {"a.py": "x = 1\n"})
        (r / ".broom.json").write_text('{"test_commands": ["just check"]}')  # not committed, as when git ignores it
        work = self.tmp / "linked"
        self.sh(r, "git", "worktree", "add", "-q", str(work), "-b", "linked")
        self.assertFalse((work / ".broom.json").exists())
        self.assertTrue(self.reaches_python("commit.sh", work, "echo hi"))
        plain = BroomCase.repo(self, {"a.py": "x = 1\n"})
        plain_work = self.tmp / "linked2"
        self.sh(plain, "git", "worktree", "add", "-q", str(plain_work), "-b", "linked2")
        self.assertFalse(self.reaches_python("commit.sh", plain_work, "echo hi"))

    def test_the_hook_files_are_in_the_manifest_with_the_timeout_of_the_others(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        (group,) = hooks["PostToolUseFailure"]
        (hook,) = group["hooks"]
        self.assertEqual((group["matcher"], hook["timeout"]), ("Bash", 30))
        self.assertTrue((ROOT / "hooks" / "failed.sh").exists())
        self.assertTrue(os.access(ROOT / "hooks" / "failed.sh", os.X_OK))


if __name__ == "__main__":
    unittest.main()
