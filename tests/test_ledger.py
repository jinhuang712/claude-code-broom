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

    def test_a_finding_that_only_changed_isnt_fixed(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        (r / "a.py").write_text(py_function("huge", 110))  # shorter, and still past the hard limit: another message
        self.sh(r, "git", "add", "a.py")
        self.assertIn("huge is 110 lines long", self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(len(lines("block")), 2)
        self.assertEqual(lines("fix"), [], "the same finding, not a fixed one")
        (r / "a.py").write_text(py_function("small", 20))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual([x["key"] for x in lines("fix")], [lines("block")[1]["key"]], "fixed under its last key")

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
    def test_a_lint_finding_blocks_again_and_again_until_it_is_fixed_or_accepted_with_a_reason(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("import os\n")
        self.sh(r, "git", "add", "a.py")
        first = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("F401", first)
        self.assertIn('run `broom known --accept "<why>"`, then commit again', first)
        self.assertNotIn("same commit again", first)
        for _ in range(4):  # no retry and no number of denials lets it through
            self.assertIn("F401", self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(lines("pass"), [])
        self.assertEqual(self.cli(r, "known", "--accept", "unused on purpose").returncode, 0)
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        (through,) = lines("pass")
        self.assertEqual((through["how"], through["why"], through["key"]), ("accept", "unused on purpose",
                                                                           lines("block")[0]["key"]))
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom let 1 through this turn: 1 F401 (accepted: unused on purpose)")

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

    def test_giving_up_ends_the_turn_and_the_ledger_and_the_summary_say_what_was_left(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        (r / "a.py").write_text(py_function("medium", 60))  # past the soft limit: a hint, which stops a turn too
        (r / "b.py").write_text(py_function("huge", 120).replace("+=", "-="))  # not a copy of a.py's
        for name in ("a.py", "b.py"):
            self.edit(r, name)
        self.assertIn("issue(s) in this turn's changes", self.stop(r)["reason"])
        self.assertEqual(sorted((x["file"], x["where"]) for x in lines("block")), [("a.py", "stop"), ("b.py", "stop")])
        for _ in range(2):
            self.assertEqual(self.stop(r).get("decision"), "block", "stopping again passes nothing")
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom GAVE UP after 3 blocks: 2 finding(s) left unfixed and unaccepted: a.py:1 "
                         "function_lines, b.py:1 function_lines; "
                         "broom let 2 through this turn: 2 function_lines (gave-up)")
        self.assertEqual(sorted((x["file"], x["how"]) for x in lines("pass")),
                         [("a.py", "gave-up"), ("b.py", "gave-up")])

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_giving_up_leaves_a_lint_finding_open_and_not_known(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("import os\n")
        self.edit(r, "a.py")
        reason = self.stop(r)["reason"]
        self.assertIn("F401", reason)
        self.assertIn('run `broom known --accept "<why>"`, then stop again', reason)
        for _ in range(2):
            self.assertIn("F401", self.stop(r)["reason"], "stopping again passes nothing")
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom GAVE UP after 3 blocks: 1 finding(s) left unfixed and unaccepted: a.py:1 F401; "
                         "broom let 1 through this turn: 1 F401 (gave-up)")
        self.assertEqual([x["how"] for x in lines("pass")], ["gave-up"])
        self.assertEqual(self.cli(r, "known").stdout.strip(), "broom: no known issues here")
        self.sh(r, "git", "add", "a.py")
        self.assertIn("F401", self.denied(self.commit(r, "git commit -m x")), "the commit still stops on it")

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_accepting_what_a_turn_end_blocked_lets_the_next_stop_through(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        (r / "a.py").write_text("import os\n")
        self.edit(r, "a.py")
        self.assertIn("F401", self.stop(r)["reason"])
        out = self.cli(r, "known", "--accept", "unused on purpose")
        self.assertEqual((out.returncode, out.stdout.strip()),
                         (0, "broom: accepted 1 issue(s) as known (unused on purpose); stop again"))
        self.assertEqual(self.cli(r, "known", "--accept", "again").returncode, 1, "nothing left to accept")
        (r / "b.py").write_text("y = 2\n")  # a new edit: the check runs again, and finds a.py's issue known
        self.edit(r, "b.py")
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom let 1 through this turn: 1 F401 (accepted: unused on purpose)")
        (through,) = lines("pass")
        self.assertEqual((through["how"], through["where"]), ("accept", "stop"))
        self.assertEqual(lines("fix"), [], "accepted is not fixed")

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_stopping_again_after_accepting_ends_the_turn_without_a_second_pass(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("import os\n")
        self.edit(r, "a.py")
        self.assertIn("F401", self.stop(r)["reason"])
        self.assertEqual(self.cli(r, "known", "--accept", "unused on purpose").returncode, 0)
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom let 1 through this turn: 1 F401 (accepted: unused on purpose)")
        self.assertEqual([x["how"] for x in lines("pass")], ["accept"], "what was accepted isn't also left unfixed")

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

    def test_a_note_at_a_commit_is_noted_and_blocks_nothing(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("x = 1  # TODO: later\n")
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        self.assertEqual([(x["rule"], x["file"]) for x in lines("hint")], [("todo", "a.py")])
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
            ledger.fixes({"k": entry}, {}, set(), files, notes)
            self.assertEqual(lines("fix"), [], (files, notes))
        ledger.fixes({"k": entry}, {}, {"k"}, [r / "a.py"], [])
        self.assertEqual(lines("fix"), [], "accepted since: not fixed")
        ledger.fixes({"k": entry}, {}, set(), [r / "a.py"], ["missing:golangci-lint (brew install golangci-lint)"])
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
