"""Test coverage: each of the four report forms read, a report's file names matched to the repo's files, what `broom
stats` says with a report, without one and with one it can't read, and the check-up's counter of lines no test
reaches."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from gitwork import GitWork

from broom import checkup, coverage

CODE = "".join(f"V{i} = {i}\n" for i in range(10))  # ten lines a report can speak of
LCOV = "TN:\nSF:{name}\nDA:1,1\nDA:2,1\nDA:3,0\nDA:4,0\nend_of_record\n"
COBERTURA = """<?xml version="1.0" ?>
<coverage version="7.4" line-rate="0.5">
  <sources><source>{source}</source></sources>
  <packages><package name="."><classes>
    <class name="a.py" filename="{name}"><lines>
      <line number="1" hits="3"/><line number="2" hits="0"/><line number="3" hits="0"/>
    </lines></class>
  </classes></package></packages>
</coverage>
"""
GO_PROFILE = "mode: set\nexample.com/demo/pkg/a.go:4.2,5.1 2 1\nexample.com/demo/pkg/a.go:8.2,9.11 3 0\n"


def lcov(name: str, reached: int, missed: int) -> str:
    """An lcov report for one file: its first `reached` lines run and the next `missed` not."""
    rows = [f"DA:{n},1" for n in range(1, reached + 1)] + [f"DA:{n},0" for n in range(reached + 1, reached + missed + 1)]
    return "\n".join([f"SF:{name}", *rows, "end_of_record", ""])


class ReportFormsTest(GitWork):
    def lines(self, r: Path, name: str, text: str) -> object:
        (r / name).parent.mkdir(parents=True, exist_ok=True)
        (r / name).write_text(text)
        return coverage.lines_of(r, r / name)

    def test_lcov_gives_the_lines_reached_and_all_of_them_per_file(self) -> None:
        r = self.repo({"a.py": CODE})
        self.assertEqual(self.lines(r, "coverage/lcov.info", LCOV.format(name="a.py")), {"a.py": (2, 4)})

    def test_a_file_that_a_report_names_twice_is_reached_where_either_run_reached_it(self) -> None:
        r = self.repo({"a.py": CODE})
        twice = lcov("a.py", 1, 3) + "SF:a.py\nDA:1,0\nDA:2,5\nend_of_record\n"
        self.assertEqual(self.lines(r, "lcov.info", twice), {"a.py": (2, 4)})

    def test_cobertura_names_its_files_from_a_source_folder(self) -> None:
        r = self.repo({"src/a.py": CODE})
        report = COBERTURA.format(source=str(r / "src"), name="a.py")
        self.assertEqual(self.lines(r, "coverage.xml", report), {"src/a.py": (1, 3)})

    def test_a_go_profile_weighs_each_block_by_its_statements_and_names_files_by_import_path(self) -> None:
        r = self.repo({"go.mod": "module example.com/demo\n", "pkg/a.go": "package pkg\n"})
        self.assertEqual(self.lines(r, "coverage.out", GO_PROFILE), {"pkg/a.go": (2, 5)})

    def test_the_json_of_coverage_py_lists_the_lines_that_ran_and_those_that_did_not(self) -> None:
        r = self.repo({"a.py": CODE})
        report = json.dumps({"meta": {}, "files": {"a.py": {"executed_lines": [1, 2, 3], "missing_lines": [4]}}})
        self.assertEqual(self.lines(r, "coverage.json", report), {"a.py": (3, 4)})

    def test_a_path_from_another_machine_is_matched_by_its_end_and_a_file_not_here_is_left_out(self) -> None:
        r = self.repo({"pkg/a.py": CODE})
        report = lcov("/ci/build/42/pkg/a.py", 1, 1) + lcov("/ci/build/42/pkg/gone.py", 1, 1)
        self.assertEqual(self.lines(r, "lcov.info", report), {"pkg/a.py": (1, 2)})

    def test_a_report_that_is_no_report_or_declares_entities_is_not_read(self) -> None:
        r = self.repo({"a.py": CODE})
        self.assertIsNone(self.lines(r, "coverage.xml", "<coverage><unclosed>"))
        bomb = '<?xml version="1.0"?><!DOCTYPE c [<!ENTITY a "aaaa">]><coverage>&a;</coverage>'
        self.assertIsNone(self.lines(r, "coverage.xml", bomb))
        self.assertIsNone(self.lines(r, "coverage.json", "{not json"))

    def test_the_newest_report_among_the_usual_places_is_the_one_read(self) -> None:
        r = self.repo({"a.py": CODE, "lcov.info": lcov("a.py", 1, 1), "coverage/lcov.info": lcov("a.py", 2, 0)})
        old = time.time() - 3600
        os.utime(r / "lcov.info", (old, old))
        self.assertEqual(coverage.report_path(r), r / "coverage/lcov.info")
        self.assertIsNone(coverage.report_path(self.repo({"a.py": CODE})))


class StatsCoverageTest(GitWork):
    def coverage_of(self, r: Path) -> dict:
        done = self.cli(r, "stats", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["tests"]["coverage"]

    def test_with_a_report_stats_gives_the_share_reached_and_the_files_with_most_lines_not_reached(self) -> None:
        report = lcov("a.py", 2, 6) + lcov("b.py", 9, 1) + lcov("c.py", 0, 3) + lcov("tests/test_a.py", 0, 9)
        r = self.repo({"a.py": CODE, "b.py": CODE, "c.py": CODE, "tests/test_a.py": CODE, "lcov.info": report})
        c = self.coverage_of(r)
        self.assertEqual((c["report"], c["unread"], c["age_days"], c["behind"]), ("lcov.info", False, 0, False))
        self.assertEqual((c["lines"], c["reached"], c["percent"], c["files"], c["unreached_files"]), (21, 11, 52, 3, 1))
        self.assertEqual(c["least"], [{"file": "a.py", "lines": 8, "missed": 6, "percent": 25},
                                      {"file": "c.py", "lines": 3, "missed": 3, "percent": 0},
                                      {"file": "b.py", "lines": 10, "missed": 1, "percent": 90}])
        text = self.cli(r, "stats").stdout
        self.assertIn("  coverage: 52% of 21 lines reached, by lcov.info (0 days old); 1 of 3 files not reached at all",
                      text)
        self.assertRegex(text, r"\n  least reached\s+lines\s+not reached\s+reached\n  a\.py\s+8\s+6\s+25%\n")
        self.assertNotIn("tests/test_a.py  ", text.split("coverage:")[1].split("\nRot")[0], "tests are left out")

    def test_a_report_older_than_the_last_commit_is_said_to_be(self) -> None:
        r = self.repo({"a.py": CODE, "lcov.info": lcov("a.py", 1, 1)})
        old = time.time() - 3 * 86400 - 60
        os.utime(r / "lcov.info", (old, old))
        c = self.coverage_of(r)
        self.assertEqual((c["age_days"], c["behind"]), (3, True))
        self.assertIn("(3 days old, older than the last commit)", self.cli(r, "stats").stdout)

    def test_without_a_report_stats_says_how_a_test_run_writes_one_for_the_languages_of_the_repo(self) -> None:
        r = self.repo({"a.py": CODE, "pkg/a.go": "package pkg\n"})
        self.assertEqual(self.coverage_of(r), {"report": None, "how": [coverage.HOW["go"], coverage.HOW["py"]]})
        text = self.cli(r, "stats").stdout
        self.assertIn("  no coverage report found (coverage.xml, lcov.info, coverage.out or coverage.json); "
                      "broom runs no tests.\n  A test run writes one with:\n    go test -coverprofile=coverage.out ./...",
                      text)
        self.assertNotIn("cargo", text)

    def test_a_report_that_cannot_be_read_is_named_as_such(self) -> None:
        r = self.repo({"a.py": CODE, "coverage.xml": "<coverage><unclosed>"})
        self.assertEqual(self.coverage_of(r), {"report": "coverage.xml", "unread": True})
        self.assertIn("  coverage: coverage.xml could not be read", self.cli(r, "stats").stdout)

    def test_the_diagnosis_shows_the_coverage_with_the_tests_section(self) -> None:
        r = self.repo({"a.py": CODE, "lcov.info": lcov("a.py", 2, 6)})
        self.assertIn("coverage: 25% of 8 lines reached, by lcov.info", self.cli(r, "diagnose").stdout)


class CheckupCoverageTest(GitWork):
    def scan(self, r: Path, session: str) -> str:
        """What the async session scan tells Claude in `session`."""
        out = self.session(r, session, self.env, "session-scan")
        return out.get("hookSpecificOutput", {}).get("additionalContext", "")

    def counter(self, r: Path) -> object:
        return json.loads(checkup.record_path(r).read_text())["counters"].get("uncovered_lines")

    def test_lines_no_test_reaches_are_counted_per_file_and_told_once_when_they_grow(self) -> None:
        r = self.repo({"a.py": CODE, "b.py": CODE, "lcov.info": lcov("a.py", 8, 2) + lcov("b.py", 10, 0)})
        self.assertEqual(self.scan(r, "s1"), "", "the first check-up takes its numbers silently")
        self.assertEqual(self.counter(r), {"a.py": 2})
        (r / "lcov.info").write_text(lcov("a.py", 8, 2) + lcov("b.py", 7, 3))
        self.assertIn("lines no test reaches, by the coverage report 2 -> 5 (b.py)", self.scan(r, "s2"))
        self.assertEqual(self.scan(r, "s3"), "", "told once")
        (r / "lcov.info").write_text(lcov("a.py", 10, 0) + lcov("b.py", 10, 0))
        self.assertEqual(self.scan(r, "s4"), "", "a number that fell says nothing")
        self.assertEqual(self.counter(r), {})

    def test_without_a_report_nothing_is_counted_and_the_diagnosis_says_not_measured(self) -> None:
        r = self.repo({"a.py": CODE})
        self.assertEqual(self.scan(r, "s1"), "")
        self.assertIsNone(self.counter(r))
        row = {c["counter"]: c for c in json.loads(self.cli(r, "diagnose", "--json").stdout)["checkup"]["counters"]}
        self.assertEqual((row["uncovered_lines"]["label"], row["uncovered_lines"]["now"]),
                         ("lines no test reaches, by the coverage report", None))

    def test_a_report_that_goes_away_keeps_the_last_number_and_says_nothing(self) -> None:
        r = self.repo({"a.py": CODE, "lcov.info": lcov("a.py", 8, 2)})
        self.scan(r, "s1")
        (r / "lcov.info").unlink()
        self.assertEqual(self.scan(r, "s2"), "")
        self.assertEqual(self.counter(r), {"a.py": 2})
