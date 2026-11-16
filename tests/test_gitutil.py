"""Asking git for what a check needs takes a few processes however many files it looks at."""

from __future__ import annotations

import unittest
from unittest import mock

from support import BroomCase

from broom import gitutil
from broom.gitutil import ChangedLines, git_root


class GitUtilTests(BroomCase):
    def test_the_repo_of_a_directory_is_found_without_starting_git(self) -> None:
        r = self.repo({"pkg/sub/a.py": "x = 1\n"})
        with mock.patch.object(gitutil, "run", side_effect=AssertionError("started a process")):
            self.assertEqual(git_root(r / "pkg" / "sub"), r.resolve())
            self.assertIsNone(git_root(self.tmp))

    def test_the_repo_is_asked_of_git_when_the_environment_points_git_somewhere(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        with mock.patch.dict("os.environ", {"GIT_DIR": str(r / ".git")}), \
                mock.patch.object(gitutil, "_git_roots", {}), \
                mock.patch.object(gitutil, "git", return_value=f"{r.resolve()}\n") as asked:
            self.assertEqual(git_root(r), r.resolve())
            asked.assert_called_once()

    def test_changed_lines_asks_git_per_repo_not_per_file(self) -> None:
        names = {f"f{i}.py": f"x = {i}\n" for i in range(20)}
        r = self.repo(names)
        (r / "f3.py").write_text("x = 3\ny = 4\nz = 5\n")
        (r / "new.py").write_text("n = 1\n")
        calls: list = []
        real = gitutil.run

        def counting(cmd, *args, **kw):
            calls.append(cmd[1:3])
            return real(cmd, *args, **kw)

        changed = ChangedLines()
        with mock.patch.object(gitutil, "run", counting):
            got = {name: changed.get(r / name) for name in [*names, "new.py"]}
        self.assertEqual(got["f3.py"], {2, 3}, "the lines it added")
        self.assertEqual(got["f0.py"], set(), "tracked and as it was")
        self.assertIsNone(got["new.py"], "untracked: all of it is new")
        self.assertLessEqual(len(calls), 6, calls)  # not 3 per file, 63 for 21 files


if __name__ == "__main__":
    unittest.main()
