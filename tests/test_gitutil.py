"""Asking git for what a check needs takes a few processes however many files it looks at."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from support import BroomCase

from broom import gitcmd, gitutil
from broom.gitutil import ChangedLines, git_root, main_worktree, tree_state


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

    def test_a_folder_is_in_the_repo_git_names_by_its_git_dir_alone_as_git_runs_its_hooks(self) -> None:
        r = self.repo({"pkg/sub/a.py": "x = 1\n"})
        linked = self.tmp / "linked"
        self.sh(r, "git", "worktree", "add", "-q", str(linked), "-b", "side")
        # A hook runs in the top of its work tree, with the worktree's own git directory and nothing else: git run in
        # a folder below would take that folder for the top.
        with mock.patch.dict("os.environ", {"GIT_DIR": self.sh(linked, "git", "rev-parse", "--absolute-git-dir").strip()}), \
                mock.patch.object(gitutil, "_git_roots", {}), mock.patch.object(Path, "cwd", return_value=linked):
            self.assertEqual(git_root(linked), linked)
            self.assertEqual(git_root(linked / "pkg" / "sub"), linked, "not the folder git was asked in")

    def test_a_folder_is_in_the_work_tree_git_names_relative_to_the_directory_it_runs_in(self) -> None:
        store, work = self.tmp / "store.git", self.tmp / "work"
        (work / "pkg").mkdir(parents=True)
        self.sh(self.tmp, "git", "init", "-q", "--bare", str(store))
        # `git --git-dir=<store> --work-tree=<work>` hands its hooks GIT_WORK_TREE=. and runs them in <work>.
        with mock.patch.dict("os.environ", {"GIT_DIR": str(store), "GIT_WORK_TREE": "."}), \
                mock.patch.object(gitutil, "_git_roots", {}), mock.patch.object(Path, "cwd", return_value=work):
            self.assertEqual(git_root(work / "pkg"), work, "`.` names the directory the hook runs in, not this folder")

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

    def test_the_main_checkout_of_a_worktree_is_found_without_starting_git(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        linked = self.tmp / "linked"
        self.sh(r, "git", "worktree", "add", "-q", str(linked), "-b", "side")
        with mock.patch.object(gitutil, "_main_roots", {}), \
                mock.patch.object(gitutil, "run", side_effect=AssertionError("started a process")):
            self.assertEqual(main_worktree(linked), r, "a linked worktree names its main checkout in git's files")
            self.assertEqual(main_worktree(r), r)

    def test_a_submodule_is_its_own_main_checkout(self) -> None:
        inner = self.repo({"lib.py": "x = 1\n"})
        r = self.repo({"a.py": "x = 1\n"})
        self.sh(r, "git", "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "vendor")
        with mock.patch.object(gitutil, "_main_roots", {}):
            self.assertEqual(main_worktree(r / "vendor"), r / "vendor", "git is asked, since the files don't say")

    def test_head_and_the_changed_files_come_from_one_git_call(self) -> None:
        r = self.repo({"kept.py": "x = 1\n", "edited.py": "x = 1\n", "staged.py": "x = 1\n", "gone.py": "x = 1\n",
                       ".gitignore": "ignored.py\n"})
        (r / "edited.py").write_text("x = 2\n")
        (r / "staged.py").write_text("x = 3\n")
        self.sh(r, "git", "add", "staged.py")
        (r / "gone.py").unlink()
        (r / "ignored.py").write_text("x = 1\n")
        for name in ("new file.py", "sub/新.py"):
            (r / name).parent.mkdir(exist_ok=True)
            (r / name).write_text("x = 1\n")
        calls: list = []
        real = gitutil.run

        def counting(cmd, *args, **kw):
            calls.append(cmd[3])  # after `git -c core.quotePath=false`
            return real(cmd, *args, **kw)

        with mock.patch.object(gitutil, "run", counting):
            head, files = tree_state(r)
        self.assertEqual(calls, ["status"])
        self.assertEqual(head, self.sh(r, "git", "rev-parse", "HEAD").strip())
        self.assertEqual({f.relative_to(r).as_posix() for f in files},
                         {"edited.py", "staged.py", "new file.py", "sub/新.py"},
                         "changed, staged and untracked; not the deleted, the ignored or the unchanged")

    def test_a_repo_with_no_commit_has_no_head_and_lists_its_files(self) -> None:
        r = self.tmp / "fresh"
        r.mkdir()
        self.sh(r, "git", "init", "-q")
        (r / "a.py").write_text("x = 1\n")
        (r / "b.py").write_text("x = 1\n")
        self.sh(r, "git", "add", "a.py")
        head, files = tree_state(r)
        self.assertEqual(head, "")
        self.assertEqual({f.name for f in files}, {"a.py", "b.py"})

    def test_a_file_with_a_non_ascii_name_is_listed_under_its_name(self) -> None:
        r = self.repo({"新.py": "x = 1\n"})
        (r / "新.py").write_text("x = 2\n")
        self.assertEqual(gitutil.changed_since(r, "HEAD"), [r / "新.py"], "not quoted and escaped, as git prints it")
        self.sh(r, "git", "add", "-A")
        self.assertEqual(gitcmd.staged(r), {r / "新.py"})


if __name__ == "__main__":
    unittest.main()
