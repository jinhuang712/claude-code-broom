"""A commit's block and a turn end's block in one repo each end once in the ledger: one fix line for each, whichever
hook sees the finding gone, and none lost because the other hook's block took the place of the last one."""

from __future__ import annotations

from pathlib import Path

from support import py_function
from test_ledger import LedgerCase, lines

SMALL = py_function("small", 20)


class OutcomeTest(LedgerCase):
    def blocked_twice(self) -> Path:
        """A repo where a commit blocked a.py and then the turn's end blocked b.py, which the turn's end alone saw."""
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.huge(r)
        self.assertIn("huge is 120", self.denied(self.commit(r, "git commit -m x")))
        (r / "b.py").write_text(py_function("huge", 120).replace("+=", "-="))  # not a copy of a.py's
        self.edit(r, "b.py")
        self.assertIn("huge is 120", self.stop(r)["reason"])
        self.assertEqual(sorted((x["file"], x["where"]) for x in lines("block")), [("a.py", "commit"), ("b.py", "stop")])
        return r

    def fixed_once_each(self) -> None:
        keys = sorted(x["key"] for x in lines("fix"))
        self.assertEqual(keys, sorted({x["key"] for x in lines("block")}), "one fix line for each block, and no more")

    def test_a_turn_end_block_doesnt_take_a_commit_blocks_fix_line_with_it(self) -> None:
        r = self.blocked_twice()
        (r / "a.py").write_text(SMALL)
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        (r / "b.py").write_text("y = 2\n")
        self.edit(r, "b.py")
        self.assertNotIn("decision", self.stop(r))
        self.assertEqual(sorted(x["file"] for x in lines("fix")), ["a.py", "b.py"])
        self.fixed_once_each()

    def test_a_turn_end_that_finds_nothing_leaves_the_commit_blocks_finding_to_the_next_commit(self) -> None:
        r = self.blocked_twice()
        (r / "b.py").write_text("y = 2\n")
        self.edit(r, "b.py")
        self.assertNotIn("decision", self.stop(r))
        self.assertEqual([x["file"] for x in lines("fix")], ["b.py"], "a.py is not the turn's to fix")
        (r / "a.py").write_text(SMALL)
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(sorted(x["file"] for x in lines("fix")), ["a.py", "b.py"])
        self.fixed_once_each()

    def test_accepting_what_the_turn_end_blocked_leaves_the_commit_blocks_finding_to_be_fixed(self) -> None:
        r = self.blocked_twice()
        out = self.cli(r, "known", "--accept", "legacy code")
        self.assertEqual((out.returncode, out.stdout.strip()),
                         (0, "broom: accepted 1 issue(s) as known (legacy code); stop again"))
        self.assertEqual([(x["file"], x["how"]) for x in lines("pass")], [("b.py", "accept")], "a.py wasn't shown")
        self.assertEqual(self.cli(r, "known", "--accept", "again").returncode, 1, "nothing left to accept")
        (r / "a.py").write_text(SMALL)
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual([x["file"] for x in lines("fix")], ["a.py"])

    def test_a_commit_and_a_turn_end_that_both_see_a_finding_gone_write_its_fix_once(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.edit(r, "a.py")
        self.assertIn("huge is 120", self.stop(r)["reason"])
        (r / "a.py").write_text(SMALL)
        self.sh(r, "git", "add", "a.py")
        self.edit(r, "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual([x["where"] for x in lines("fix")], ["commit"])
        self.assertNotIn("decision", self.stop(r))
        self.assertEqual([x["where"] for x in lines("fix")], ["commit"], "the turn's end saw it gone as well")

    def test_a_finding_fixed_blocked_again_and_fixed_again_has_a_fix_line_each_time(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        for _ in range(2):
            self.huge(r)
            self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
            (r / "a.py").write_text(SMALL)
            self.sh(r, "git", "add", "a.py")
            self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual([x["event"] for x in lines() if x["event"] in ("block", "fix")],
                         ["block", "fix", "block", "fix"])
