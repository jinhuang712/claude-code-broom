"""F2.13 at a turn's end: a turn that changed code and shows no test run after the change, or whose last test run failed, is
blocked like any finding, and passes fixed, accepted for its turn only, or put to the user."""

from __future__ import annotations

import json
import unittest

from test_asked import six
from test_nowave import QUIET
from test_testrun import GIVE_UP, NOT_RUN_LINE, TEST_FILE_TEXT, TestRunCase


class TurnEndTest(TestRunCase):
    def test_a_turn_that_changed_code_and_ran_no_test_is_blocked(self) -> None:
        r = self.code_repo()
        self.change(r)
        out = self.stop(r)
        self.assertEqual(out.get("decision"), "block")
        reason = out["reason"]
        self.assertTrue(reason.startswith("[broom] 1 issue(s) in this turn's changes. Fix them before finishing."), reason)
        self.assertIn(f"tests ({r}):\n  {NOT_RUN_LINE}", reason)
        self.assertIn("  tests_not_run: Run the project's tests, then stop again.", reason)
        self.assertIn('run `broom known --accept "<why>"`, then stop again.', reason)
        self.assertTrue(reason.endswith("Block 1 of 3. After 3 blocks the turn ends, and the user is told what is "
                                        "still open."), reason)

    def test_the_same_turn_with_a_test_command_started_after_the_change_is_not_blocked(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.assertEqual(self.stop(r).get("decision"), "block")
        self.bash(r, "python3 -m pytest -q")
        self.assertEqual(self.stop(r), {})
        self.assertEqual([x["rule"] for x in self.ledger_rows("fix")], ["tests_not_run"], "it was fixed, and says so")

    def test_an_edit_after_the_test_run_blocks_again(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.bash(r, "npm test")
        self.change(r, "x = 3\n")
        out = self.stop(r)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn(NOT_RUN_LINE, out["reason"])
        self.assertIn("Block 1 of 3", out["reason"])

    def test_a_test_run_that_started_before_the_first_change_is_no_trace_of_it(self) -> None:
        r = self.code_repo()
        self.bash(r, "pytest")
        self.change(r)
        self.assertIn(NOT_RUN_LINE, self.stop(r)["reason"])

    def test_a_failed_test_run_blocks_with_its_exit_code_and_a_later_passing_run_clears_it(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.bash(r, "pytest -q")
        self.failed(r, "pytest -q", "Exit code 1\n1 failed")
        out = self.stop(r)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("  a.py  tests_failed  the last test run failed: Exit code 1, `pytest -q`", out["reason"])
        self.assertIn("  tests_failed: Fix what fails; if it fails for a reason outside this change, say so to the "
                      "user.", out["reason"])
        self.assertNotIn("tests_not_run", out["reason"], "one finding, not two")
        self.bash(r, "pytest -q")
        self.assertEqual(self.stop(r), {})

    def test_the_last_test_run_that_started_decides_not_an_earlier_failure(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.bash(r, "pytest tests/test_a.py")
        self.failed(r, "pytest tests/test_a.py")
        self.bash(r, "npm test")
        self.assertEqual(self.stop(r), {}, "another command started after the failure and has none")

    def test_a_repo_that_tracks_no_test_file_is_never_blocked(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.change(r)
        self.assertEqual(self.stop(r), {})

    def test_a_test_file_in_a_dependency_or_fixture_folder_is_no_test_of_the_project(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "vendor/dep/dep_test.go": "package dep\n", "pkg/testdata/a_test.go": "package a\n"})
        self.change(r)
        self.assertEqual(self.stop(r), {})

    def test_a_test_file_that_is_only_untracked_does_not_count(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "tests").mkdir()
        (r / "tests" / "test_a.py").write_text(TEST_FILE_TEXT)
        self.change(r)
        self.assertEqual(self.stop(r), {}, "the repo tracks none yet")

    def test_a_turn_that_changed_only_a_file_that_is_no_code_is_never_blocked(self) -> None:
        r = self.code_repo(**{"docs/notes.md": "a\n"})
        self.change(r, "b\n", "docs/notes.md")
        self.assertEqual(self.stop(r), {})

    def test_a_turn_that_changed_only_a_test_file_is_blocked_too(self) -> None:
        r = self.code_repo()
        self.change(r, TEST_FILE_TEXT + "\n\ndef test_b():\n    assert True\n", "tests/test_a.py")
        self.assertIn("tests_not_run", self.stop(r)["reason"])

    def test_smells_off_with_the_rules_name_turns_both_findings_off(self) -> None:
        r = self.code_repo(**{".broom.json": '{"smells_off": ["dead_code", "missing_docs", "tests_not_run"]}'})
        self.change(r)
        self.assertEqual(self.stop(r), {})
        self.new_turn(r)
        self.change(r, "x = 3\n")
        self.bash(r, "pytest")
        self.failed(r, "pytest")
        self.assertEqual(self.stop(r), {}, "a failed run too")

    def test_no_turn_end_check_means_no_rule(self) -> None:
        for check_on in ("commit", "off"):
            r = self.code_repo(**{".broom.json": json.dumps({"check_on": check_on})})
            self.change(r)
            self.assertEqual(self.stop(r), {}, check_on)

    def test_a_test_command_a_repo_names_counts(self) -> None:
        r = self.code_repo(**{".broom.json": '{"smells_off": ["dead_code", "missing_docs"], "test_commands": ["just check"]}'})
        self.change(r)
        self.bash(r, "just build")
        self.assertEqual(self.stop(r).get("decision"), "block", "no other word is a test run")
        self.bash(r, "just check --all")
        self.assertEqual(self.stop(r), {})

    def test_a_subagents_end_never_raises_it(self) -> None:
        r = self.code_repo()
        agent = {"session_id": "s1", "cwd": str(r), "agent_id": "ag1"}
        (r / "a.py").write_text("x = 5\n")
        self.hook("edit", {**agent, "tool_name": "Edit", "tool_input": {"file_path": str(r / "a.py")}})
        self.assertEqual(self.hook("subagent-stop", {**agent, "permission_mode": "default"}), {}, "no test ran in it")
        self.change(r)
        self.assertEqual(self.stop(r).get("decision"), "block", "the session's own end does raise it")

    def test_a_test_run_of_a_subagent_counts_for_the_session(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.hook("commit", {"session_id": "s1", "cwd": str(r), "agent_id": "ag1", "tool_name": "Bash",
                             "tool_input": {"command": "pytest"}})
        self.assertEqual(self.stop(r), {})

    def test_a_commit_never_raises_it(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})


class OneTurnTest(TestRunCase):
    def test_an_accept_passes_this_turn_and_the_next_turns_end_raises_it_again(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.assertEqual(self.stop(r).get("decision"), "block")
        out = self.cli(r, "known", "--accept", "only a comment changed")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.stop(r), {"systemMessage": "broom let 1 through this turn: 1 tests_not_run (accepted: "
                                                         "only a comment changed)"})
        self.assertEqual(self.cli(r, "known").stdout.strip(), "broom: no known issues here", "no known issue")
        self.assertEqual([x["rule"] for x in self.ledger_rows("fix")], [], "accepted is no fix")
        self.new_turn(r)
        self.change(r, "x = 3\n")
        out = self.stop(r)
        self.assertEqual(out.get("decision"), "block", "again, when again no test ran")
        self.assertIn("Block 1 of 3", out["reason"])

    def test_an_accept_holds_for_the_rest_of_the_turn_whatever_is_edited_after_it(self) -> None:
        r = self.code_repo(**{"b.py": "y = 1\n"})
        self.change(r)
        self.assertEqual(self.stop(r).get("decision"), "block")
        self.assertEqual(self.cli(r, "known", "--accept", "no test for it").returncode, 0)
        self.change(r, "y = 2\n", "b.py")
        self.assertIn("1 tests_not_run (accepted: no test for it)", self.stop(r)["systemMessage"])

    def test_a_failed_run_accepted_for_a_reason_outside_the_change_passes_this_turn_only(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.bash(r, "pytest")
        self.failed(r, "pytest")
        self.assertEqual(self.stop(r).get("decision"), "block")
        self.assertEqual(self.cli(r, "known", "--accept", "fails on the main branch too", "--agreed").returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": "broom let 1 through this turn: 1 tests_failed (accepted, the "
                                                         "user agreed: fails on the main branch too)"})
        self.assertEqual(self.cli(r, "known").stdout.strip(), "broom: no known issues here")

    def test_asking_ends_the_turn_with_the_question_and_the_finding_blocks_again_at_the_next_turn(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.assertEqual(self.stop(r).get("decision"), "block")
        out = self.cli(r, "known", "--ask", "May this change go untested?")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.stop(r), {"systemMessage": "broom: 1 finding WAITS FOR YOUR ANSWER: a.py tests_not_run: "
                                                         "May this change go untested?"})
        self.new_turn(r)
        self.change(r, "x = 4\n")
        self.assertEqual(self.stop(r).get("decision"), "block")

    def test_the_report_counts_it_blocked_then_fixed(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.assertEqual(self.stop(r).get("decision"), "block")
        self.bash(r, "pytest")
        self.assertEqual(self.stop(r), {})
        data = json.loads(self.cli(r, "report", "--json").stdout)
        self.assertEqual((data["blocked"], data["fixed"], data["open"], data["let_through"]), (1, 1, 0, 0))

    def test_it_counts_toward_the_three_blocks_and_the_give_up_and_shows_in_the_ledger(self) -> None:
        r = self.code_repo()
        self.change(r)
        for n in (1, 2, 3):
            out = self.stop(r)
            self.assertEqual(out.get("decision"), "block", n)
            self.assertIn(f"Block {n} of 3.", out["reason"])
        self.assertEqual(self.stop(r), {"systemMessage": GIVE_UP})
        self.assertEqual([(x["tool"], x["rule"], x["file"]) for x in self.ledger_rows("block")][:1],
                         [("tests", "tests_not_run", "a.py")])
        self.assertEqual([(x["how"], x["rule"]) for x in self.ledger_rows("pass")], [("gave-up", "tests_not_run")])

    def test_three_findings_accepted_on_its_own_open_the_line_loudly_with_this_one_among_them(self) -> None:
        r = self.code_repo(**{".broom.json": QUIET})
        self.change(r, six("one", "two"))
        self.assertEqual(self.stop(r).get("decision"), "block")
        self.assertEqual(self.cli(r, "known", "--accept", "legacy").returncode, 0)
        self.assertIn("broom: Claude ACCEPTED 3 findings this turn on its own:", self.stop(r)["systemMessage"])


if __name__ == "__main__":
    unittest.main()
