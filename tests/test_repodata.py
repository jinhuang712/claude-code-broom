"""What broom finds in a repo lives in the repo's `.broom/`, which git ignores: a moved repo keeps it, a linked
worktree shares the main checkout's, a tracked one is never read, and the old shared records move in once."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from support import BroomCase, py_function

from broom import report


class RepoDataCase(BroomCase):
    def huge(self, r: Path, name: str = "a.py") -> None:
        """A function past the hard limit, staged: it blocks a commit."""
        (r / name).write_text(py_function("huge", 120))
        self.sh(r, "git", "add", name)

    def blocked(self, r: Path) -> str:
        return self.denied(self.commit(r, "git commit -m x"))

    def numbers(self, r: Path) -> tuple:
        out = self.cli(r, "report", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        return data["blocked"], data["fixed"], data["let_through"], data["open"]


class RepoDataTest(RepoDataCase):
    def test_a_moved_repo_keeps_its_known_issues_and_its_report(self) -> None:
        r = self.repo({"b.py": "x = 1\n"})
        self.huge(r)
        self.assertTrue(self.blocked(r))
        self.assertEqual(self.cli(r, "known", "--accept", "legacy code").returncode, 0)
        self.assertEqual(self.sh(r, "git", "status", "--porcelain"), "A  a.py\n", "git ignores the folder")
        before = self.numbers(r)
        moved = self.tmp / "elsewhere" / "repo"
        moved.parent.mkdir()
        shutil.move(str(r), str(moved))
        self.assertEqual(self.blocked(moved), "", "the known issue is known where the repo went")
        self.assertEqual(self.numbers(moved), before)
        self.assertTrue(before[0] and before[0] == before[2], "what was blocked was let through")

    def test_what_a_linked_worktree_accepts_is_known_on_the_main_checkout(self) -> None:
        r = self.repo({"b.py": "x = 1\n"})
        linked = self.tmp / "linked"
        self.sh(r, "git", "worktree", "add", "-q", str(linked), "-b", "side")
        self.huge(linked)
        self.assertTrue(self.blocked(linked))
        self.assertEqual(self.cli(linked, "known", "--accept", "legacy code").returncode, 0)
        self.assertFalse((linked / ".broom").exists(), "the worktree keeps nothing of its own")
        stored = json.loads((r / ".broom" / "baseline.json").read_text())
        self.assertEqual({e["file"] for e in stored.values()}, {"a.py"}, "by its path in the repo, with no mapping")
        self.huge(r)
        self.assertEqual(self.blocked(r), "", "known in the main checkout")

    def test_a_tracked_folder_is_never_read_and_the_spare_one_is_noted(self) -> None:
        r = self.repo({"b.py": "x = 1\n"})
        self.huge(r)
        self.assertTrue(self.blocked(r))
        self.assertEqual(self.cli(r, "known", "--accept", "legacy code").returncode, 0)
        came = self.repo({"b.py": "x = 1\n", ".broom/baseline.json": (r / ".broom" / "baseline.json").read_text(),
                          ".broom/keep.txt": "x\n"})
        self.huge(came)
        self.assertTrue(self.blocked(came), "the entries that came with the repo hide nothing")
        self.assertEqual(json.loads((came / ".broom" / "baseline.json").read_text()),
                         json.loads((r / ".broom" / "baseline.json").read_text()), "and broom never writes them")
        out = self.session(came, "s2", self.env)
        self.assertIn("git tracks files in this repo's .broom/", self.noted(out))


class ReportAllTest(RepoDataCase):
    def test_report_all_sums_every_indexed_repo(self) -> None:
        repos = [self.repo({"b.py": "x = 1\n"}) for _ in range(2)]
        for r in repos:
            self.huge(r)
            self.assertTrue(self.blocked(r))
        each = [self.numbers(r)[0] for r in repos]
        with mock.patch.object(report, "TEMP_ROOTS", ()):
            data = report.report([])
        self.assertEqual((data["repos"], data["blocked"], data["open"]), ("all", sum(each), sum(each)))
        self.assertTrue(all(each))


if __name__ == "__main__":
    unittest.main()
