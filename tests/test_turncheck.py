"""The check at a turn's end: it blocks once, and stopping again ends the turn with what is left still open."""

from __future__ import annotations

import unittest

from support import HAS_PY, BroomCase, py_function

from broom import ledger


class TurnCheckTest(BroomCase):
    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_stop_mode_blocks_once_then_accepts(self) -> None:
        r = self.repo({"a.py": "def f(x):\n    return x\n"})
        (r / "a.py").write_text("import os\n\ndef f(x):\n    return x\n")
        edit = {"session_id": "s2", "cwd": str(r), "tool_name": "Edit", "tool_input": {"file_path": str(r / "a.py")}}
        stop = {"session_id": "s2", "cwd": str(r), "permission_mode": "default"}
        self.hook("edit", edit, check_on="commit")
        self.assertEqual(self.hook("stop", stop, check_on="commit"), {}, "check_on=commit leaves the turn end alone")
        self.hook("edit", edit)
        out = self.hook("stop", stop)
        self.assertEqual(out.get("decision"), "block", "the turn-end check is on by default")
        self.assertIn("F401", out["reason"])
        self.assertIn("left unfixed", self.hook("stop", stop).get("systemMessage", ""))

    def test_with_accepting_off_the_turn_end_says_so_and_a_second_stop_still_ends_the_turn(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.env["BROOM_NO_ACCEPT"] = "1"
        edit = {"session_id": "s1", "cwd": str(r), "tool_name": "Edit", "tool_input": {"file_path": str(r / "a.py")}}
        stop = {"session_id": "s1", "cwd": str(r), "permission_mode": "default"}
        self.hook("edit", edit)
        reason = self.hook("stop", stop)["reason"]
        self.assertIn("accepting them is off here (BROOM_NO_ACCEPT)", reason)
        self.assertNotIn("broom known --accept", reason, "Claude isn't told to do what it can't")
        self.assertIn("left unfixed", self.hook("stop", stop)["systemMessage"], "broom never traps a turn")

    def test_a_turn_blocked_three_times_ends_at_the_fourth_stop_with_what_is_left_on_record(self) -> None:
        r = self.repo({".broom.json": '{"smells_off": ["dead_code"]}', "a.py": "x = 1\n"})
        edit = {"session_id": "g1", "cwd": str(r), "tool_name": "Edit", "tool_input": {"file_path": str(r / "a.py")}}
        stop = {"session_id": "g1", "cwd": str(r), "permission_mode": "default"}
        for attempt in range(3):  # each edit leaves the function past the hard limit
            (r / "a.py").write_text(py_function("huge", 120 + attempt))
            self.hook("edit", edit)
            self.assertEqual(self.hook("stop", stop).get("decision"), "block", f"block {attempt + 1}")
        (r / "a.py").write_text(py_function("huge", 130))
        self.hook("edit", edit)
        self.assertEqual(self.hook("stop", stop)["systemMessage"],
                         "broom let 1 through this turn: 1 function_lines (gave-up); "
                         "gave up after 3 rounds, 1 issue(s) left")
        (through,) = [row for row in ledger.read(ledger.LEDGER) if row["event"] == "pass"]
        self.assertEqual((through["how"], through["where"]), ("gave-up", "stop"))
        self.assertEqual(self.hook("stop", stop), {}, "the turn is over")


if __name__ == "__main__":
    unittest.main()
