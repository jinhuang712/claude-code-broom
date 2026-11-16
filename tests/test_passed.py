"""Content that passed a check isn't checked again, file by file."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from support import BroomCase

from broom import commitgate, passed
from broom.findings import Issue
from broom.smells import Smell


def hint(repo: Path, file: Path) -> Smell:
    return Smell(repo, file, 1, "todo", "", 1, None, "ruff", "hint", 1)


class PassedTests(BroomCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo_dir = self.repo({"a.py": "x = 1\n", "b.py": "y = 2\n", "c.py": "z = 3\n"})
        self.files = [(self.repo_dir / n).resolve() for n in ("a.py", "b.py", "c.py")]
        self.patches = [mock.patch.object(passed, "PASSED", self.tmp / "passed.json"),
                        mock.patch.object(commitgate, "baseline_keys", return_value=set())]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        super().tearDown()

    def check(self, hints=(), blocking=(), notes=()) -> list:
        """Run `checked` with fake tools; the files the checks were asked about."""
        asked = []

        def run_checks(files, _slow):
            asked.append(sorted(f.name for f in files))
            return list(blocking), []

        with mock.patch.object(commitgate, "run_checks", run_checks), \
                mock.patch.object(commitgate, "select", lambda issues, *_a: list(issues)), \
                mock.patch.object(commitgate, "gate_smells", lambda repo, group, *_a: ([], list(hints), list(notes))):
            commitgate.checked(list(self.files), self.tmp / "sd")
        return asked

    def test_a_file_with_a_hint_doesnt_keep_the_clean_ones_from_being_recorded(self) -> None:
        a = self.files[0]
        self.assertEqual(self.check(hints=[hint(self.repo_dir, a)]), [["a.py", "b.py", "c.py"]])
        self.assertEqual(self.check(hints=[hint(self.repo_dir, a)]), [["a.py"]], "b and c passed: only a again")

    def test_a_blocked_file_is_checked_again_and_the_clean_ones_are_not(self) -> None:
        b = self.files[1]
        issue = Issue("ruff", self.repo_dir, b, 1, 1, "E1", "bad")
        self.assertEqual(self.check(blocking=[issue]), [["a.py", "b.py", "c.py"]])
        self.assertEqual(self.check(blocking=[issue]), [["b.py"]])

    def test_a_finding_outside_the_files_records_nothing(self) -> None:
        elsewhere = Issue("tsc", self.repo_dir, (self.repo_dir / "other.py").resolve(), 1, 1, "TS1", "type error")
        self.check(blocking=[elsewhere])
        self.assertEqual(self.check(blocking=[elsewhere]), [["a.py", "b.py", "c.py"]])

    def test_a_timeout_records_nothing(self) -> None:
        self.check(notes=["timeout:ruff in /x"])
        self.assertEqual(self.check(notes=["timeout:ruff in /x"]), [["a.py", "b.py", "c.py"]])

    def test_clean_content_is_not_checked_again(self) -> None:
        self.check()
        self.assertEqual(self.check(), [], "every file passed: nothing runs")


if __name__ == "__main__":
    unittest.main()
