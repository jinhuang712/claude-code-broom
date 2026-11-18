"""F2.13, judged by content: a file of the turn is tested when a test run that didn't fail tested the content it has now,
whatever its modification time says. Work tested in a linked worktree and merged, a touched file and a file restored are
tested; a file changed after the run is not."""

from __future__ import annotations

import os
import time
import unittest

from test_testrun import NOT_RUN_TEXT, TestRunCase

from broom.testtree import blobs_at, snapshot


class ContentTest(TestRunCase):
    def not_run(self, *names: str) -> str:
        """The finding line of a turn whose untested files are `names`."""
        return f"  {names[0]}  tests_not_run  {NOT_RUN_TEXT}: {', '.join(names)}"

    def test_work_tested_in_a_linked_worktree_and_merged_into_the_main_checkout_is_tested(self) -> None:
        main = self.code_repo()
        self.new_turn(main)
        work = self.tmp / "linked"
        self.sh(main, "git", "worktree", "add", "-q", str(work), "-b", "feature")
        self.change(work, "x = 2\n")
        self.bash(work, "python3 -m pytest -q")
        self.sh(work, "git", "commit", "-qam", "feature")
        time.sleep(0.05)
        self.sh(main, "git", "merge", "-q", "--ff-only", "feature")
        self.assertGreater((main / "a.py").stat().st_mtime, self.runs()[-1]["t"], "the merge is newer than the run")
        self.assertEqual(self.stop(main), {})

    def test_a_change_merged_into_the_main_checkout_that_was_never_tested_is_blocked_naming_the_file(self) -> None:
        main = self.code_repo()
        self.new_turn(main)
        work = self.tmp / "linked"
        self.sh(main, "git", "worktree", "add", "-q", str(work), "-b", "feature")
        self.change(work, "x = 2\n")
        self.sh(work, "git", "commit", "-qam", "feature")
        self.sh(main, "git", "merge", "-q", "--ff-only", "feature")
        self.assertIn(self.not_run("a.py"), self.stop(main)["reason"])

    def test_a_file_only_touched_after_the_run_is_still_tested(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.bash(r, "pytest")
        self.change(r)  # the same content, written again
        later = time.time() + 60
        os.utime(r / "a.py", (later, later))
        self.assertEqual(self.stop(r), {})

    def test_a_file_whose_content_changed_after_the_run_is_blocked_and_named(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.bash(r, "pytest")
        self.change(r, "x = 3\n")
        self.assertIn(self.not_run("a.py"), self.stop(r)["reason"])

    def test_two_files_changed_with_the_run_between_the_edits_name_only_the_second(self) -> None:
        r = self.code_repo(**{"b.py": "y = 1\n"})
        self.change(r)
        self.bash(r, "pytest")
        self.change(r, "y = 2\n", "b.py")
        reason = self.stop(r)["reason"]
        self.assertIn(self.not_run("b.py"), reason)
        self.assertNotIn("a.py", reason)

    def test_a_finding_names_three_files_and_counts_the_rest_and_sits_on_the_first_in_path_order(self) -> None:
        r = self.code_repo(**{f"{n}.py": "y = 1\n" for n in "bcde"})
        for n in "edcba":
            self.change(r, "y = 2\n", f"{n}.py")
        reason = self.stop(r)["reason"]
        self.assertIn("  a.py  tests_not_run  no test ran after the last change to code: a.py, b.py, c.py and 2 more",
                      reason)

    def test_a_file_changed_and_then_restored_to_the_tested_content_is_tested(self) -> None:
        r = self.code_repo()
        self.change(r, "x = 2\n")
        self.bash(r, "pytest")
        self.change(r, "x = 3\n")
        self.change(r, "x = 2\n")
        self.assertEqual(self.stop(r), {})

    def test_a_file_changed_back_to_what_the_repo_has_is_tested_by_a_run_on_a_clean_tree(self) -> None:
        r = self.code_repo()
        self.bash(r, "pytest")
        self.change(r, "x = 3\n")
        self.change(r, "x = 1\n")
        self.assertEqual(self.stop(r), {}, "the run tested the content HEAD has")

    def test_a_file_the_turn_deleted_needs_no_test_of_its_own(self) -> None:
        r = self.code_repo(**{"b.py": "y = 1\n"})
        self.change(r)
        self.bash(r, "pytest")
        self.change(r, "y = 2\n", "b.py")
        (r / "b.py").unlink()
        self.assertEqual(self.stop(r), {})

    def test_a_turn_that_only_deleted_code_is_not_blocked(self) -> None:
        r = self.code_repo(**{"b.py": "y = 1\n"})
        self.new_turn(r)
        (r / "b.py").unlink()
        self.assertEqual(self.stop(r), {})

    def test_a_repo_with_no_commit_yet_is_covered_by_a_run_on_the_files_as_they_are_on_disk(self) -> None:
        r = self.tmp / "fresh"
        (r / "tests").mkdir(parents=True)
        (r / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
        self.sh(r, "git", "init", "-q")
        self.sh(r, "git", "add", "tests/test_a.py")
        self.change(r, '"""A module."""\n')
        self.bash(r, "pytest")
        self.assertEqual(self.runs()[-1]["repos"][0]["head"], "")
        self.assertIn("a.py", self.runs()[-1]["repos"][0]["dirty"])
        self.assertNotIn("decision", self.stop(r), "a slight note about dead code is no block")
        self.change(r, '"""Another module."""\n')
        self.assertIn(self.not_run("a.py"), self.stop(r)["reason"])

    def test_a_test_run_in_another_repo_covers_nothing_here(self) -> None:
        r, other = self.code_repo(), self.code_repo()
        self.change(r)
        self.bash(other, "pytest")
        self.assertIn(self.not_run("a.py"), self.stop(r)["reason"])

    def test_a_cd_in_the_command_says_which_repo_it_tests(self) -> None:
        r, other = self.code_repo(), self.code_repo()
        self.change(other)
        self.bash(r, f"cd {other} && pytest -q")
        self.assertEqual(self.stop(r), {}, "the run was in the other repo, where the change is")
        self.change(other, "x = 3\n")
        self.bash(r, "pytest")
        self.assertIn(self.not_run("a.py"), self.stop(r)["reason"], "a run here covers nothing there")

    def test_a_failed_run_is_no_test_of_the_content_it_ran_on_after_the_file_changes_again(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.bash(r, "pytest")
        self.failed(r, "pytest")
        self.change(r, "x = 3\n")
        reason = self.stop(r)["reason"]
        self.assertIn(self.not_run("a.py"), reason)
        self.assertNotIn("tests_failed", reason, "what ran failed, and that content is gone")

    def test_a_failed_run_on_one_of_two_files_leaves_the_failure_when_the_other_is_untested_too(self) -> None:
        r = self.code_repo(**{"b.py": "y = 1\n"})
        self.change(r)
        self.change(r, "y = 2\n", "b.py")
        self.bash(r, "pytest")
        self.failed(r, "pytest")
        self.assertIn("tests_failed", self.stop(r)["reason"])

    def test_a_later_passing_run_after_a_failed_one_clears_it(self) -> None:
        r = self.code_repo()
        self.change(r)
        self.bash(r, "pytest")
        self.failed(r, "pytest")
        self.change(r, "x = 3\n")
        self.bash(r, "pytest")
        self.assertEqual(self.stop(r), {})


class NoteTest(TestRunCase):
    def test_a_test_start_notes_head_and_the_blobs_of_the_files_that_differ_and_none_for_the_rest(self) -> None:
        r = self.code_repo(**{"b.py": "y = 1\n"})
        self.bash(r, "pytest")
        clean = self.runs()[-1]["repos"][0]
        head = self.sh(r, "git", "rev-parse", "HEAD").strip()
        self.assertEqual((clean["head"], clean["dirty"], clean["main"]), (head, {}, str(r)))
        self.change(r, "x = 2\n")
        (r / "new.py").write_text("z = 1\n")
        self.bash(r, "pytest")
        dirty = self.runs()[-1]["repos"][0]["dirty"]
        self.assertEqual(sorted(dirty), ["a.py", "new.py"], "b.py equals HEAD: no row")
        self.assertEqual(dirty["a.py"], self.sh(r, "git", "hash-object", "a.py").strip())

    def test_a_linked_worktree_notes_the_main_checkout_as_its_repo(self) -> None:
        main = self.code_repo()
        work = self.tmp / "linked"
        self.sh(main, "git", "worktree", "add", "-q", str(work), "-b", "feature")
        self.bash(work, "pytest")
        self.assertEqual(self.runs()[-1]["repos"][0]["main"], str(main))

    def test_the_note_at_a_test_start_costs_one_git_call_on_a_clean_tree_and_two_on_a_dirty_one(self) -> None:
        r = self.code_repo()
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Bash", "tool_input": {"command": "pytest"}}
        git, _ = self.counted("commit", payload, r)
        self.assertEqual(len(git), 1, git)
        (r / "a.py").write_text("x = 2\n")
        git, _ = self.counted("commit", payload, r)
        self.assertEqual(len(git), 2, git)

    def test_blobs_at_reads_a_commit_in_one_call_and_leaves_a_missing_path_out(self) -> None:
        r = self.code_repo()
        found = blobs_at(r, self.sh(r, "git", "rev-parse", "HEAD").strip(), ["a.py", "nope.py"])
        self.assertEqual(found, {"a.py": self.sh(r, "git", "hash-object", "a.py").strip()})
        self.assertEqual(blobs_at(r, "", ["a.py"]), {})

    def test_the_snapshot_of_a_repo_is_what_the_hook_notes(self) -> None:
        r = self.code_repo()
        self.assertEqual(snapshot(r)["dirty"], {})


if __name__ == "__main__":
    unittest.main()
