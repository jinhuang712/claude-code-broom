"""The ledger: a line for every block, fix, pass and skip, the turn summary the user sees, and `broom report`."""

from __future__ import annotations

import json
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from support import BROOM, HAS_PY, BroomCase, py_function

from broom import checks, ledger

DAY = 86400
QUIET = '{"smells_off": ["dead_code"]}'  # a function nothing calls is dead code too: not what these tests are about


def lines(event: str = "") -> list:
    return [r for r in ledger.read(ledger.LEDGER) if not event or r["event"] == event]


class LedgerCase(BroomCase):
    def repo(self, files: dict) -> Path:
        return super().repo({".broom.json": QUIET, **files})

    def huge(self, r: Path, name: str = "a.py") -> None:
        """A function past the hard limit, staged: it blocks a commit, and never passes on a retry."""
        (r / name).write_text(py_function("huge", 120))
        self.sh(r, "git", "add", name)

    def stop(self, r: Path, session: str = "s1") -> dict:
        return self.hook("stop", {"session_id": session, "cwd": str(r), "permission_mode": "default"})

    def edit(self, r: Path, name: str, session: str = "s1") -> None:
        self.hook("edit", {"session_id": session, "cwd": str(r), "tool_name": "Edit",
                           "tool_input": {"file_path": str(r / name)}})


class RecordTest(LedgerCase):
    def test_a_block_and_then_a_fix_leave_a_line_each(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        self.assertIn("huge is 120 lines long", self.denied(self.commit(r, "git commit -m x")))
        (block,) = lines("block")
        self.assertEqual((block["repo"], block["where"], block["tool"], block["rule"], block["file"]),
                         (str(r), "commit", "smells", "function_lines", "a.py"))
        self.assertEqual(lines("fix"), [], "nothing is fixed yet")
        (r / "a.py").write_text(py_function("small", 20))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        (fix,) = lines("fix")
        self.assertEqual((fix["key"], fix["rule"], fix["where"]), (block["key"], "function_lines", "commit"))

    def test_a_commit_of_other_files_fixes_nothing(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.huge(r)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        (r / "b.py").write_text("y = 2\n")
        self.sh(r, "git", "add", "b.py")
        self.sh(r, "git", "restore", "--staged", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(lines("fix"), [], "a.py wasn't checked: its finding stays open")

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_a_retry_passes_a_lint_finding_and_the_ledger_says_how(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("import os\n")
        self.sh(r, "git", "add", "a.py")
        self.assertIn("F401", self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        self.assertEqual([(x["rule"], x["tool"]) for x in lines("block")], [("F401", "ruff")])
        (through,) = lines("pass")
        self.assertEqual((through["how"], through["key"]), ("retry", lines("block")[0]["key"]))
        self.assertEqual(self.stop(r)["systemMessage"], "broom let 1 through this turn: 1 F401 (retry)")

    def test_accepting_with_a_reason_is_a_pass_with_the_reason(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.cli(r, "known", "--accept", "legacy code").returncode, 0)
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        (through,) = lines("pass")
        self.assertEqual((through["how"], through["why"], through["where"]), ("accept", "legacy code", "commit"))
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom let 1 through this turn: 1 function_lines (accepted: legacy code)")
        self.assertEqual(self.stop(r), {}, "the turn is over: its summary is said once")

    def test_stopping_again_ends_the_turn_and_the_ledger_and_the_summary_say_what_was_left(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        (r / "a.py").write_text(py_function("medium", 60))  # past the soft limit: a hint, which stops a turn once
        (r / "b.py").write_text(py_function("huge", 120).replace("+=", "-="))  # not a copy of a.py's
        for name in ("a.py", "b.py"):
            self.edit(r, name)
        self.assertIn("issue(s) in this turn's changes", self.stop(r)["reason"])
        self.assertEqual(sorted((x["file"], x["where"]) for x in lines("block")), [("a.py", "stop"), ("b.py", "stop")])
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom let 2 through this turn: 1 function_lines (stop-again), "
                         "1 function_lines (turn-ended); 2 issue(s) left unfixed")
        self.assertEqual(sorted((x["file"], x["how"]) for x in lines("pass")),
                         [("a.py", "stop-again"), ("b.py", "turn-ended")])

    def test_a_finding_fixed_during_the_turn_is_a_fix_at_the_stop(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.edit(r, "a.py")
        self.assertIn("huge is 120", self.stop(r)["reason"])
        (r / "a.py").write_text(py_function("small", 20))
        self.edit(r, "a.py")
        self.assertNotIn("decision", self.stop(r))
        (block,), (fix,) = lines("block"), lines("fix")
        self.assertEqual((fix["key"], fix["where"]), (block["key"], "stop"))

    def test_a_hint_at_a_commit_is_noted_and_blocks_nothing(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("medium", 60))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        self.assertEqual([(x["rule"], x["file"]) for x in lines("hint")], [("function_lines", "a.py")])
        self.assertEqual(lines("block"), [])

    def test_a_tool_that_didnt_run_leaves_a_skip_and_a_fix_waits_for_it(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.env = self.fake_path()  # no ruff
        (r / "a.py").write_text("y = 1\n")
        self.sh(r, "git", "add", "a.py")
        self.commit(r, "git commit -m x")
        (skip,) = [x for x in lines("skip") if x["tool"] == "ruff"]
        self.assertEqual(skip["note"], "missing:ruff (brew install ruff)")
        self.commit(r, "git commit -m y")
        self.assertEqual(len([x for x in lines("skip") if x["tool"] == "ruff"]), 1, "recorded once per session")
        entry = {"file": str(r / "a.py"), "tool": "ruff", "rule": "F401"}
        for files, notes in (([r / "a.py"], [skip["note"]]), ([r / "b.py"], []), ([r / "a.py"], ["timeout:ruff in x"])):
            ledger.fixes({"k": entry}, set(), files, notes)
            self.assertEqual(lines("fix"), [], (files, notes))
        ledger.fixes({"k": entry}, {"k"}, [r / "a.py"], [])
        self.assertEqual(lines("fix"), [], "accepted since: not fixed")
        ledger.fixes({"k": entry}, set(), [r / "a.py"], ["missing:golangci-lint (brew install golangci-lint)"])
        self.assertEqual([x["key"] for x in lines("fix")], ["k"], "a note about another tool holds nothing back")

    def test_a_smell_waits_for_the_tool_that_measures_it(self) -> None:
        py, go = {"file": "a.py", "tool": "smells", "rule": "magic_numbers"}, {"file": "a.go", "tool": "smells"}
        size = {"file": "a.py", "tool": "smells", "rule": "function_lines"}
        self.assertTrue(ledger.covers("missing:ruff (brew install ruff)", py))
        self.assertFalse(ledger.covers("missing:ruff (brew install ruff)", size), "Python's own parser measures it")
        self.assertFalse(ledger.covers("missing:ruff (brew install ruff)", go))
        self.assertTrue(ledger.covers("timeout:ruff measuring smells", size))
        self.assertTrue(ledger.covers("missing:golangci-lint (brew install golangci-lint)", go))

    def test_the_time_of_each_check_is_noted_for_a_hook_and_not_otherwise(self) -> None:
        tool = ("ruff:/x", lambda: ([], []))
        with mock.patch.object(checks, "plan", return_value=[tool]):
            checks.run_checks([Path("a.py")])
            self.assertEqual(lines("time"), [])
            checks.run_checks([Path("a.py")], self.tmp / "slow.json")
        (took,) = lines("time")
        self.assertEqual((took["check"], took["repo"]), ("ruff", "/x"))
        self.assertEqual(took["seconds"], round(took["seconds"], 2))

    def test_a_hook_that_failed_leaves_an_error_line_and_lets_the_action_through(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        bad = {"session_id": "s1", "cwd": str(r), "tool_name": "Edit", "tool_input": "not an object"}
        out = subprocess.run([str(BROOM), "hook", "edit"], input=json.dumps(bad), capture_output=True, text=True,
                             env=self.env, cwd=r)
        self.assertEqual((out.returncode, out.stdout), (0, ""))
        (error,) = lines("error")
        self.assertEqual((error["where"], error["repo"]), ("edit", str(r)))
        self.assertIn("AttributeError", error["note"])

    def test_the_turn_summary_groups_what_was_let_through(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        turn = self.tmp / "turn"
        turn.mkdir()
        magic = {str(n): {"file": str(r / "a.py"), "tool": "smells", "rule": "magic_numbers"} for n in range(2)}
        ledger.let_through(magic, "retry", turn)
        ledger.let_through({"k": {"file": str(r / "a.py"), "tool": "smells", "rule": "function_lines"}}, "accept", turn,
                           why="legacy")
        self.assertEqual(ledger.through_line(turn),
                         "broom let 3 through this turn: 2 magic_numbers (retry), 1 function_lines (accepted: legacy)")
        ledger.forget_through(turn)
        self.assertEqual(ledger.through_line(turn), "", "a turn that let nothing through says nothing")

    def test_a_turn_no_stop_hook_ended_doesnt_leak_its_summary_into_the_next(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.cli(r, "known", "--accept", "legacy code")
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})
        self.assertEqual(self.stop(r), {}, "the new prompt started a turn that let nothing through")

    def test_the_ledger_stays_bounded_and_a_ledger_that_cant_be_written_stops_nothing(self) -> None:
        old, now = time.time() - 100 * DAY, time.time()
        pad = "k" * 40
        rows = [{"t": t, "repo": "/a", "event": "block", "key": pad} for t in (old, now)]
        ledger.LEDGER.parent.mkdir(parents=True, exist_ok=True)
        ledger.LEDGER.write_text("".join(json.dumps(x) + "\n" for x in rows))
        with mock.patch.object(ledger, "MAX_BYTES", 300):
            ledger.write([{"t": now, "repo": "/a", "event": "fix", "key": pad}])
        self.assertEqual([x["event"] for x in lines()], ["block", "fix"], "the line older than 90 days is gone")
        with mock.patch.object(ledger, "MAX_BYTES", 1000):
            ledger.write([{"t": now, "repo": "/a", "event": "pass", "key": str(n)} for n in range(50)])
        self.assertLess(ledger.LEDGER.stat().st_size, 1000, "recent lines go too, the oldest first, when it is over")
        self.assertEqual(lines()[-1]["key"], "49")
        blocker = self.tmp / "file"
        blocker.write_text("")
        with mock.patch.object(ledger, "LEDGER", blocker / "ledger.jsonl"):
            ledger.write([{"t": now, "repo": "/a", "event": "fix"}])  # its directory is a file: no error


if __name__ == "__main__":
    unittest.main()
