"""The check-up: the first numbers are the baseline and silent, a counter that grew is told once with the files that
added to it, one that fell is silent, `broom diagnose` lists them all, and `smells_off` turns it off. Sample code is
written as lists of lines, and the markers in two pieces: broom reads its own tests too."""

from __future__ import annotations

import json
import shutil
import unittest
from datetime import date
from pathlib import Path

from gitwork import GitWork, days_ago
from support import HAS_PY, py_function

from broom import checkup
from broom.gitutil import CLOCK

NOQA = "# no" + "qa: E501"
TELL = "At a natural point tell the user; don't interrupt their task. `broom diagnose` shows where each number sits."


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


def suppressed(n: int) -> str:
    """A file with `n` lint suppressions."""
    return text(*(f"x{i} = 1  {NOQA}" for i in range(n)))


def skipped(n: int) -> str:
    """A test file with `n` skipped tests."""
    return text("import unittest", "", *(f'@unittest.skip("later")\ndef test_{i}():\n    pass\n' for i in range(n)))


class CheckupCase(GitWork):
    def setUp(self) -> None:
        super().setUp()
        self.bare = self.fake_path()  # no linter and no jscpd: only the counters that need no tool are counted

    def scan(self, r: Path, session: str, env: dict = None) -> str:
        """What the async session scan tells Claude in `session`."""
        out = self.session(r, session, env or self.bare, "session-scan")
        return out.get("hookSpecificOutput", {}).get("additionalContext", "")

    def record(self, r: Path) -> dict:
        return json.loads(checkup.record_path(r).read_text())["counters"]

    def diagnose(self, r: Path, *args: str, env: dict = None) -> dict:
        done = self.cli(r, "diagnose", "--json", *args, env=env or self.bare)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["checkup"]


class TellingTest(CheckupCase):
    def test_the_first_numbers_are_the_baseline_and_nothing_is_said(self) -> None:
        r = self.repo({"a.py": suppressed(2), "tests/test_a.py": skipped(1)})
        self.assertEqual(self.scan(r, "s1"), "")
        counters = self.record(r)
        self.assertEqual(counters["suppressions"], {"a.py": 2})
        self.assertEqual(counters["skipped_tests"], {"tests/test_a.py": 1})
        self.assertEqual(sorted(counters), ["old_todos", "skipped_tests", "suppressions"],
                         "a counter whose tool is missing has no number to keep")

    def test_a_counter_that_grew_is_told_once_with_its_files_and_the_new_numbers_become_the_baseline(self) -> None:
        r = self.repo({"a.py": suppressed(1), "tests/test_x.py": skipped(2)})
        self.scan(r, "s1")
        self.commit_all(r, {"b.py": suppressed(2), "tests/test_x.py": skipped(3)})
        self.assertEqual(self.scan(r, "s2"),
                         "broom check-up: lint suppressions 1 -> 3 (b.py); skipped tests 2 -> 3 (tests/test_x.py). " + TELL)
        self.assertEqual(self.scan(r, "s2"), "", "once, in the same session")
        self.assertEqual(self.scan(r, "s3"), "", "and in the next ones")
        self.assertEqual(self.record(r)["suppressions"], {"a.py": 1, "b.py": 2})

    def test_numbers_another_version_of_broom_took_are_no_baseline_to_grow_from(self) -> None:
        r = self.repo({"a.py": suppressed(1)})
        self.scan(r, "s1")
        path = checkup.record_path(r)
        path.write_text(json.dumps({**json.loads(path.read_text()), "version": "0.0.1"}))
        self.commit_all(r, {"b.py": suppressed(2)})
        self.assertEqual(self.scan(r, "s2"), "", "what an older broom counted may be something else: start over")
        self.commit_all(r, {"c.py": suppressed(1)})
        self.assertIn("lint suppressions 3 -> 4 (c.py)", self.scan(r, "s3"), "and from then on growth is told")

    def test_it_runs_on_the_working_tree_when_the_scan_of_head_is_cached(self) -> None:
        r = self.repo({"a.py": suppressed(1)})
        self.scan(r, "s1")
        (r / "a.py").write_text(suppressed(2))  # not committed: HEAD, and so the cached scan, stay as they were
        self.assertIn("lint suppressions 1 -> 2 (a.py)", self.scan(r, "s2"))

    def test_a_number_that_fell_is_recorded_silently_and_growth_is_set_against_it(self) -> None:
        r = self.repo({"a.py": suppressed(1), "b.py": suppressed(2)})
        self.scan(r, "s1")
        self.commit_all(r, {"b.py": "y = 1\n"})
        self.assertEqual(self.scan(r, "s2"), "")
        self.assertEqual(self.record(r)["suppressions"], {"a.py": 1})
        self.commit_all(r, {"b.py": suppressed(2)})
        self.assertIn("lint suppressions 1 -> 3 (b.py)", self.scan(r, "s3"), "from the number it fell to")

    def test_a_number_that_did_not_change_is_silent(self) -> None:
        r = self.repo({"a.py": suppressed(1)})
        self.scan(r, "s1")
        self.commit_all(r, {"b.py": "y = 1\n"})
        self.assertEqual(self.scan(r, "s2"), "")

    def test_the_note_names_three_files_and_says_how_many_more(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.scan(r, "s1")
        self.commit_all(r, {f"{name}.py": suppressed(1) for name in "abcde"})
        self.assertIn("lint suppressions 0 -> 5 (a.py, b.py, c.py and 2 more)", self.scan(r, "s2"))

    def test_the_files_that_added_most_come_first(self) -> None:
        r = self.repo({"a.py": suppressed(1), "b.py": "x = 1\n"})
        self.scan(r, "s1")
        self.commit_all(r, {"a.py": suppressed(2), "b.py": suppressed(3)})
        self.assertIn("lint suppressions 1 -> 5 (b.py, a.py)", self.scan(r, "s2"))

    def test_a_todo_counts_once_it_is_older_than_180_days(self) -> None:
        r = self.history_repo([(400, {"a.py": "x = 1\n"})])
        self.scan(r, "s1")
        self.commit_all(r, {"c.py": "# TODO: recent\n"}, days_ago(1))
        self.assertEqual(self.scan(r, "s2"), "", "a TODO of yesterday is not old")
        self.commit_all(r, {"b.py": "# TODO: old\n"}, days_ago(300))
        self.assertIn("TODO comments older than 180 days 0 -> 1 (b.py)", self.scan(r, "s3"))

    def test_a_worktree_and_its_main_checkout_share_one_record(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        linked = self.tmp / "linked"
        self.sh(r, "git", "worktree", "add", "-q", str(linked), "-b", "side")
        self.assertEqual(checkup.record_path(linked), checkup.record_path(r))

    def test_the_hook_with_little_time_left_leaves_the_check_up_to_the_next_session(self) -> None:
        self.addCleanup(lambda: setattr(CLOCK, "end", None))
        r = self.repo({"a.py": suppressed(1)})
        CLOCK.start(checkup.MIN_SECONDS - 1)
        self.assertIsNone(checkup.check_up_time(r, {"counts": {}}))
        self.assertFalse(checkup.record_path(r).exists())


class OffTest(CheckupCase):
    def test_smells_off_holding_checkup_turns_it_off_and_leaves_the_smell_note(self) -> None:
        r = self.repo({"a.py": py_function("huge", 120), ".broom.json": '{"smells_off": ["checkup"]}'})
        note = self.scan(r, "s1")
        self.assertIn("clean skill", note, "the smell note is not the check-up")
        self.assertNotIn("check-up", note)
        self.assertFalse(checkup.record_path(r).exists(), "nothing was counted or kept")
        self.assertTrue(self.diagnose(r)["off"])

    def test_the_smells_setting_at_off_turns_it_off_too(self) -> None:
        r = self.repo({"a.py": suppressed(1), ".broom.json": '{"smells": "off"}'})
        self.assertEqual(self.scan(r, "s1"), "")
        self.assertFalse(checkup.record_path(r).exists())
        self.assertTrue(self.diagnose(r)["off"])

    def test_turning_it_on_again_takes_the_numbers_of_that_day_as_the_baseline_silently(self) -> None:
        r = self.repo({"a.py": suppressed(1), ".broom.json": '{"smells_off": ["checkup"]}'})
        self.scan(r, "s1")
        (r / ".broom.json").write_text("{}")
        self.assertEqual(self.scan(r, "s2"), "")
        self.assertEqual(self.record(r)["suppressions"], {"a.py": 1})


class DiagnoseTest(CheckupCase):
    def test_every_counter_is_listed_now_and_at_the_last_check_up_grown_or_not(self) -> None:
        r = self.repo({"a.py": suppressed(1), "tests/test_x.py": skipped(2)})
        self.scan(r, "s1")
        self.commit_all(r, {"b.py": suppressed(2)})
        d = self.diagnose(r)
        self.assertEqual((d["off"], d["narrowed"], d["last"]), (False, False, date.today().isoformat()))
        rows = {c["counter"]: c for c in d["counters"]}
        self.assertEqual(list(rows), ["suppressions", "skipped_tests", "old_todos", "dead_code", "missing_docs",
                                      "deprecated_api", "duplicate_tests", "uncovered_lines"])
        self.assertEqual(rows["suppressions"], {"counter": "suppressions", "label": "lint suppressions", "now": 3,
                                                "was": 1, "grew": True, "files": ["b.py"]})
        self.assertEqual((rows["skipped_tests"]["now"], rows["skipped_tests"]["was"], rows["skipped_tests"]["grew"]),
                         (2, 2, False))
        self.assertEqual((rows["dead_code"]["now"], rows["dead_code"]["was"]), (None, None), "no jscpd: not measured")
        self.assertEqual(self.record(r)["suppressions"], {"a.py": 1}, "the diagnosis keeps nothing")
        self.assertIn("lint suppressions 1 -> 3", self.scan(r, "s2"), "so the session still tells it")

    def test_the_report_has_a_check_up_section_with_a_table(self) -> None:
        r = self.repo({"a.py": suppressed(1)})
        self.scan(r, "s1")
        self.commit_all(r, {"b.py": suppressed(2)})
        out = self.cli(r, "diagnose", env=self.bare).stdout
        section = out.split("## Check-up\n")[1].split("\n\n## ")[0].splitlines()
        self.assertEqual(section[0], f"  Last check-up: {date.today().isoformat()}")
        self.assertRegex(section[1], r"^  counter\s+now\s+at the last check-up\s+change$")
        self.assertRegex(section[2], r"^  lint suppressions\s+3\s+1\s+grew \(b\.py\)$")
        self.assertRegex(section[3], r"^  skipped tests\s+0\s+0\s+same$")
        self.assertRegex(out, r"\n  dead-code findings\s+-\s+-\s+not measured\n")
        self.assertLess(out.index("## The worst smells"), out.index("## Check-up"))
        self.assertLess(out.index("## Check-up"), out.index("## Size"))

    def test_without_a_check_up_yet_the_report_says_so(self) -> None:
        r = self.repo({"a.py": suppressed(1)})
        out = self.cli(r, "diagnose", env=self.bare).stdout
        self.assertIn("## Check-up\n  No check-up has run here yet.", out)
        self.assertIsNone(self.diagnose(r)["last"])

    def test_a_diagnosis_of_some_paths_counts_them_and_has_no_last_check_up_to_set_against(self) -> None:
        r = self.repo({"a.py": suppressed(1), "b.py": suppressed(2)})
        self.scan(r, "s1")
        d = self.diagnose(r, "a.py")
        self.assertEqual((d["narrowed"], d["last"]), (True, None))
        self.assertEqual({c["counter"]: (c["now"], c["was"]) for c in d["counters"]}["suppressions"], (1, None))
        out = self.cli(r, "diagnose", "a.py", env=self.bare).stdout
        self.assertIn("Counted within the paths given", out)

    def test_a_repo_with_the_check_up_off_says_so(self) -> None:
        r = self.repo({"a.py": "x = 1\n", ".broom.json": '{"smells_off": ["checkup"]}'})
        out = self.cli(r, "diagnose", env=self.bare).stdout
        self.assertIn("## Check-up\n  off in this repo", out)


@unittest.skipUnless(HAS_PY and shutil.which("jscpd"), "ruff or jscpd missing")
class WholeRepoCountersTest(CheckupCase):
    UTIL = text('"""Helpers."""', "", "", "def helper():", '    """Help."""', "    return 1")

    def repo_with_code(self) -> Path:
        return self.repo({"main.py": text('"""Run."""', "", "from pkg.util import helper", "", "print(helper())"),
                          "pkg/__init__.py": "", "pkg/util.py": self.UTIL})

    def test_dead_code_and_public_code_with_no_comment_are_counted_in_the_whole_repo_and_told_when_they_grow(self) -> None:
        r = self.repo_with_code()
        self.assertEqual(self.scan(r, "s1", self.env), "")
        counters = self.record(r)
        self.assertEqual((counters["dead_code"], counters["missing_docs"]), ({}, {}))
        self.commit_all(r, {"pkg/util.py": self.UTIL + text("", "", "def orphan():", "    return 2")})
        note = self.scan(r, "s2", self.env)
        self.assertIn("dead-code findings 0 -> 1 (pkg/util.py)", note)
        self.assertIn("public code with no doc comment 0 -> 1 (pkg/util.py)", note)
        self.assertEqual(self.scan(r, "s3", self.env), "")

    def test_old_dead_code_and_old_missing_comments_are_in_the_whole_repo_count_not_only_added_lines(self) -> None:
        r = self.repo({"main.py": text("from pkg.util import helper", "", "print(helper())"), "pkg/__init__.py": "",
                       "pkg/util.py": text("VALUE = 1", "", "", "def helper():", "    return VALUE", "", "", "def orphan():", "    return 2")})
        self.scan(r, "s1", self.env)
        counters = self.record(r)
        self.assertEqual(counters["missing_docs"], {"main.py": 1, "pkg/util.py": 3})
        self.assertEqual(counters["dead_code"], {"pkg/util.py": 1}, "`orphan`, though no change added it")
        self.assertEqual(self.scan(r, "s2", self.env), "", "and they were not told: they are the baseline")
