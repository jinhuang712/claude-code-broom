"""A commit's block and a turn end's block in one repo each end once in the ledger: one fix line for each, whichever
hook sees the finding gone, and none lost because the other hook's block took the place of the last one."""

from __future__ import annotations

from pathlib import Path

from support import py_function
from test_ledger import LedgerCase, lines

from broom import gate
from broom.state import load_json

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

    def other_files_blocked(self) -> Path:
        """A repo where a commit blocked a.py, and a later commit took b.py alone and passed."""
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n", "c.py": "z = 1\n"})
        self.huge(r)
        self.assertIn("huge is 120", self.denied(self.commit(r, "git commit -m x")))
        self.take_alone(r, "b.py", "y = 2\n")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        return r

    def take_alone(self, r: Path, name: str, text: str) -> None:
        """Stage `name` with `text` and nothing else: the next commit takes no other file."""
        (r / name).write_text(text)
        self.sh(r, "git", "add", name)
        for other in sorted(set(self.sh(r, "git", "diff", "--cached", "--name-only").split()) - {name}):
            self.sh(r, "git", "restore", "--staged", other)

    def kept(self, r: Path) -> dict:
        """The findings commits.json keeps for `r` besides the last block's."""
        return (load_json(gate.COMMITS, {}).get(str(r)) or {}).get("earlier") or {}

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

    def test_giving_up_leaves_nothing_for_a_later_accept_to_pass_a_second_time(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.edit(r, "a.py")
        for _ in range(3):
            self.assertIn("huge is 120", self.stop(r)["reason"])
        self.assertIn("1 finding(s) left unfixed and unaccepted", self.stop(r)["systemMessage"])
        self.assertEqual([x["how"] for x in lines("pass")], ["gave-up"])
        out = self.cli(r, "known", "--accept", "late")
        self.assertEqual(out.returncode, 1, "the turn ended: its finding is let through already")
        self.assertEqual([x["how"] for x in lines("pass")], ["gave-up"], "one outcome for the one block")
        self.assertEqual(self.cli(r, "known").stdout.strip(), "broom: no known issues here")

    def test_a_clean_commit_of_other_files_keeps_a_blocked_finding_for_the_commit_that_covers_it(self) -> None:
        r = self.other_files_blocked()
        self.assertEqual(lines("fix"), [], "a.py wasn't checked: its finding stays open")
        self.take_alone(r, "a.py", SMALL)
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual([x["file"] for x in lines("fix")], ["a.py"])
        self.fixed_once_each()

    def test_a_blocking_commit_of_other_files_keeps_a_blocked_finding_for_the_commit_that_covers_it(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.huge(r)
        self.assertIn("huge is 120", self.denied(self.commit(r, "git commit -m x")))
        self.take_alone(r, "b.py", py_function("huge", 120).replace("+=", "-="))  # not a copy of a.py's
        self.assertIn("huge is 120", self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(lines("fix"), [])
        self.take_alone(r, "b.py", "y = 2\n")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual([x["file"] for x in lines("fix")], ["b.py"], "a.py is still open")
        self.take_alone(r, "a.py", SMALL)
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(sorted(x["file"] for x in lines("fix")), ["a.py", "b.py"])
        self.fixed_once_each()

    def test_what_a_commit_kept_cant_be_accepted_by_the_next_one(self) -> None:
        r = self.other_files_blocked()
        self.assertEqual(self.cli(r, "known", "--accept", "late").returncode, 1, "the last block showed nothing")
        self.assertEqual(lines("pass"), [])
        self.assertEqual(len(self.kept(r)), 1, "a.py's finding is still there to be fixed")

    def test_the_record_lets_go_of_a_finding_whose_file_is_gone(self) -> None:
        r = self.other_files_blocked()
        self.assertEqual(len(self.kept(r)), 1)
        self.sh(r, "git", "rm", "-qf", "a.py")
        self.take_alone(r, "c.py", "z = 2\n")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(self.kept(r), {}, "nothing left to fix: the file is gone")

    def test_the_record_lets_go_of_a_finding_accepted_since(self) -> None:
        r = self.other_files_blocked()
        gate.baseline_add_entries(self.kept(r))
        self.take_alone(r, "c.py", "z = 2\n")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(self.kept(r), {}, "known now: no fix line will ever be written for it")
        self.assertEqual(lines("fix"), [])

    def test_a_commit_that_replaces_a_turn_end_block_leaves_its_finding_to_the_turns_own_end(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.edit(r, "a.py")
        self.assertIn("huge is 120", self.stop(r)["reason"])
        self.take_alone(r, "b.py", py_function("huge", 120).replace("+=", "-="))  # not a copy of a.py's
        self.assertIn("huge is 120", self.denied(self.commit(r, "git commit -m x")))
        for _ in range(2):
            self.assertEqual(self.stop(r).get("decision"), "block", "stopping again passes nothing")
        self.assertEqual(self.stop(r)["systemMessage"].count("gave-up"), 1, "a.py's finding ends with the turn")
        self.take_alone(r, "b.py", "y = 2\n")
        self.sh(r, "git", "add", "b.py")
        (r / "a.py").write_text(SMALL)
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(sorted((x["file"], x["event"]) for x in lines() if x["event"] in ("fix", "pass")),
                         [("a.py", "pass"), ("b.py", "fix")], "one outcome for each block")
