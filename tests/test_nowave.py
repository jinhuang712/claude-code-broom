"""Goal R5, nothing is waved through: a finding that is more than slight passes a commit or a turn's end only fixed or
accepted with a reason, trying again passes nothing, and after three blocks broom lets go and says so loudly."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from support import BroomCase, py_function

from broom import ledger
from broom.findings import Issue
from broom.report import report
from broom.turncheck import gave_up_line

QUIET = '{"smells_off": ["dead_code", "missing_docs"]}'  # not what these tests are about
MEDIUM = py_function("medium", 60)  # past the soft limit and under the hard one: a hint
GIVE_UP = ("broom GAVE UP after 3 blocks: 1 finding(s) left unfixed and unaccepted: a.py:1 function_lines; "
           "broom let 1 through this turn: 1 function_lines (gave-up)")


def passes() -> list:
    """The pass lines of the ledger, as (how, rule)."""
    return [(r["how"], r["rule"]) for r in ledger.read(ledger.LEDGER) if r["event"] == "pass"]


class NoWaveCase(BroomCase):
    def setUp(self) -> None:
        super().setUp()
        # The broom of the Claude Code session running the tests must not stand in for the one under test.
        dirs = self.env["PATH"].split(os.pathsep)
        self.env["PATH"] = os.pathsep.join(p for p in dirs if not (Path(p) / "broom").exists())

    def repo(self, files: dict) -> Path:
        return super().repo({".broom.json": QUIET, **files})

    def staged(self, r: Path, text: str) -> None:
        """Write `text` to a.py and stage it."""
        (r / "a.py").write_text(text)
        self.sh(r, "git", "add", "a.py")

    def edit(self, r: Path) -> None:
        self.hook("edit", {"session_id": "s1", "cwd": str(r), "tool_name": "Edit",
                           "tool_input": {"file_path": str(r / "a.py")}})

    def stop(self, r: Path) -> dict:
        return self.hook("stop", {"session_id": "s1", "cwd": str(r), "permission_mode": "default"})


class CommitTest(NoWaveCase):
    def test_a_commit_whose_only_finding_is_a_hint_is_denied_and_passes_after_a_fix(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.staged(r, MEDIUM)
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertTrue(reason.startswith("[broom] Commit blocked: 1 issue(s) in the files being committed."), reason)
        self.assertIn("medium is 60 lines long (over 50; new)", reason)
        self.assertIn("Trying again passes nothing: only a fix does, or accepting with a reason.", reason)
        self.assertIn('run `broom known --accept "<why>"`, then commit again.', reason)
        for _ in range(3):
            self.assertIn("medium is 60 lines long", self.denied(self.commit(r, "git commit -m x")), "no retry passes")
        self.assertEqual(passes(), [])
        self.staged(r, py_function("small", 20))
        self.assertEqual(self.commit(r, "git commit -m x"), {})

    def test_a_commit_whose_only_finding_is_a_hint_passes_after_an_accept_with_a_reason(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.staged(r, MEDIUM)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.cli(r, "known", "--accept", "a long one by design").returncode, 0)
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(passes(), [("accept", "function_lines")])

    def test_a_hint_and_a_block_stop_a_commit_in_one_report(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.staged(r, MEDIUM + "\n\n" + py_function("huge", 120).replace("+=", "-="))
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("Commit blocked: 2 issue(s)", reason)
        self.assertIn("medium is 60 lines long (over 50; new)", reason)
        self.assertIn("huge is 120 lines long (hard limit 100; new)", reason)

    def test_a_commit_whose_only_finding_is_a_note_passes_with_the_note_in_its_context(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.staged(r, "x = 1  # TODO: later\n")
        out = self.commit(r, "git commit -m x")
        self.assertEqual(self.denied(out), "")
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("1 slight code smell(s) this change made worse; nothing stops on them", context)
        self.assertIn("a.py:1 1 more TODO/FIXME comment(s)", context)
        self.assertEqual([(x["rule"], x["file"]) for x in ledger.read(ledger.LEDGER) if x["event"] == "hint"],
                         [("todo", "a.py")])

    def test_with_accepting_off_a_hint_says_only_a_fix_passes(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.staged(r, MEDIUM)
        self.env["BROOM_NO_ACCEPT"] = "1"
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("Trying again passes nothing. Fixing is the only way out: accepting them is off here", reason)
        self.assertNotIn("broom known --accept", reason)

    def test_git_pre_commit_denies_on_a_hint_and_passes_it_once_accepted(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.assertEqual(self.cli(r, "install-hook").returncode, 0)
        self.staged(r, MEDIUM)
        out = subprocess.run(["git", "commit", "-qm", "x"], cwd=r, env=self.env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("medium is 60 lines long (over 50; new)", out.stderr)
        self.assertIn("Trying again passes nothing", out.stderr)
        self.assertEqual(self.cli(r, "known", "--accept", "a long one by design").returncode, 0)
        out = subprocess.run(["git", "commit", "-qm", "x"], cwd=r, env=self.env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)


class TurnEndTest(NoWaveCase):
    def blocked_thrice(self, r: Path) -> None:
        """Stop three times after one edit: each stop blocks, with no new edit in between."""
        self.edit(r)
        for n in (1, 2, 3):
            out = self.stop(r)
            self.assertEqual(out.get("decision"), "block", f"stop {n}")
            self.assertIn("medium is 60 lines long (over 50; new)", out["reason"], f"stop {n}")
            self.assertIn("Trying again passes nothing", out["reason"], f"stop {n}")
            self.assertTrue(out["reason"].endswith("After 3 blocks the turn ends, and the user is told what is still "
                                                   "open."), f"stop {n}")

    def test_a_turns_end_blocks_three_times_without_an_edit_and_gives_up_on_the_fourth_stop(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(MEDIUM)
        self.blocked_thrice(r)
        self.assertEqual(passes(), [], "nothing is let through while it blocks")
        out = self.stop(r)
        self.assertEqual(out, {"systemMessage": GIVE_UP})
        self.assertEqual(passes(), [("gave-up", "function_lines")])
        self.assertEqual(self.stop(r), {}, "the turn is over")
        self.assertEqual(self.cli(r, "known").stdout.strip(), "broom: no known issues here", "given up is not known")
        self.assertEqual(self.cli(r, "known", "--accept", "late").returncode, 1, "and there is nothing left to accept")

    def test_with_accepting_off_the_same_give_up_happens(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(MEDIUM)
        self.env["BROOM_NO_ACCEPT"] = "1"
        self.edit(r)
        for _ in range(3):
            reason = self.stop(r)["reason"]
            self.assertIn("Trying again passes nothing. Fixing is the only way out: accepting them is off here", reason)
            self.assertNotIn("broom known --accept", reason, "Claude isn't told to do what it can't")
        self.assertEqual(self.stop(r), {"systemMessage": GIVE_UP})
        self.assertEqual(passes(), [("gave-up", "function_lines")])

    def test_a_finding_fixed_between_blocks_ends_the_turn_without_a_give_up(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(MEDIUM)
        self.edit(r)
        self.assertEqual(self.stop(r).get("decision"), "block")
        self.assertEqual(self.stop(r).get("decision"), "block")
        (r / "a.py").write_text(py_function("small", 20))
        self.edit(r)
        self.assertEqual(self.stop(r), {})
        self.assertEqual(passes(), [])
        self.assertEqual([x["event"] for x in ledger.read(ledger.LEDGER) if x["event"] in ("block", "fix")],
                         ["block", "block", "fix"])

    def test_a_hint_accepted_at_a_turns_end_doesnt_block_again(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(MEDIUM)
        self.edit(r)
        self.assertEqual(self.stop(r).get("decision"), "block")
        self.assertEqual(self.cli(r, "known", "--accept", "a long one by design").returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": "broom let 1 through this turn: 1 function_lines "
                                                         "(accepted: a long one by design)"})
        self.assertEqual(self.stop(r), {}, "and not again")
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {}, "nor at the commit")
        self.assertEqual(passes(), [("accept", "function_lines")])

    def test_a_note_never_blocks_a_turns_end_and_is_told_once(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("x = 1  # TODO: later\n")
        self.edit(r)
        self.assertEqual(self.stop(r), {"systemMessage": "broom: 1 slight smell(s) noted: a.py:1 todo"})
        self.assertEqual(self.stop(r), {}, "the turn is over, and the note was told")

    def test_a_note_is_told_once_at_the_end_of_a_turn_that_blocked_before(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        todo = "y = 2  # TODO: later\n"
        (r / "a.py").write_text(todo + MEDIUM)
        self.edit(r)
        for _ in range(2):
            self.assertNotIn("todo", self.stop(r)["reason"], "a note is no part of a block")
        (r / "a.py").write_text(todo + py_function("small", 20))
        self.edit(r)
        self.assertEqual(self.stop(r), {"systemMessage": "broom: 1 slight smell(s) noted: a.py:1 todo"})
        self.assertEqual(self.stop(r), {}, "told once")


class ReportTest(NoWaveCase):
    def test_old_lines_that_hold_turn_ended_are_still_read_by_broom_report(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        row = {"t": time.time(), "repo": str(r), "where": "stop", "tool": "smells", "rule": "function_lines",
               "file": "a.py"}
        ledger.write([{**row, "event": event, "key": key, **({"how": how} if event == "pass" else {})}
                      for key, how in (("k1", "turn-ended"), ("k2", "gave-up")) for event in ("block", "pass")])
        data = report([r], 30)
        self.assertEqual((data["blocked"], data["let_through"], data["how"]), (2, 2, {"turn-ended": 1, "gave-up": 1}))
        self.assertIn("(gave-up 1, turn-ended 1)", self.cli(r, "report").stdout)


class GaveUpLineTest(BroomCase):
    def test_the_line_names_the_first_five_findings_and_counts_the_rest(self) -> None:
        root = Path("/r")
        issues = [Issue("smells", root, root / f"f{n}.py", n, 0, "function_lines", "x") for n in range(7, 0, -1)]
        self.assertEqual(gave_up_line(issues),
                         "broom GAVE UP after 3 blocks: 7 finding(s) left unfixed and unaccepted: f1.py:1 "
                         "function_lines, f2.py:2 function_lines, f3.py:3 function_lines, f4.py:4 function_lines, "
                         "f5.py:5 function_lines, and 2 more")


if __name__ == "__main__":
    import unittest

    unittest.main()
