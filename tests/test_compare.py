"""broom compare: the smells of a repo now against a revision, on throwaway repos with no linter and no jscpd on the
PATH so that what is found is the same on every machine: the counts by kind, the smells that are gone, new,
smaller and bigger (a renamed file matched to its old path), how the hotspots of the base moved, the line to quote,
the checkout removed again however it ends, and a tool that ran in one measuring and not in the other."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import mock

from gitwork import GitWork
from support import py_function

from broom import compare, rowcache
from broom.smell import Smell
from broom.state import short_hash


def one(name: str, lines: int, op: str = "+=") -> str:
    """A Python function `name`, `lines` long, with the operator `op`, so that no two are copies."""
    return py_function(name, lines).replace("+=", op)


class CompareTest(GitWork):
    def setUp(self) -> None:
        super().setUp()
        self.bare = self.fake_path()

    def worked_repo(self) -> Path:
        """Five smells at tag `v1`; then a fix, a rename, a shrunk and a grown function and a new one, the last of
        them (the shrunk function) not committed."""
        r = self.history_repo([(300, {"a.py": one("huge", 120), "b.py": one("medium", 60, "-="),
                                      "c.py": one("shrink", 130, "*="), "d.py": one("grow", 70, "|="),
                                      "f.py": one("fixed", 55, "^=")})])
        self.sh(r, "git", "tag", "v1")
        self.sh(r, "git", "mv", "b.py", "pkg_b.py")
        (r / "a.py").write_text("def huge(x):\n    return x\n")
        (r / "f.py").write_text("def fixed(x):\n    return x\n")
        (r / "d.py").write_text(one("grow", 90, "|="))
        (r / "e.py").write_text(one("newcomer", 120, "&="))
        self.sh(r, "git", "add", "-A")
        self.sh(r, "git", "commit", "-qm", "work")
        (r / "c.py").write_text(one("shrink", 90, "*="))
        return r

    def compare(self, r: Path, *args: str) -> dict:
        done = self.cli(r, "compare", "v1", "--json", *args, env=self.bare)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def names(self, rows: list) -> list:
        return sorted(re.sub(r" is \d+ code lines.*", "", x["text"]) for x in rows)

    def test_the_churn_of_a_base_counts_the_commits_up_to_it(self) -> None:
        r = self.history_repo([(30, {"a.py": "x = 1\n"}), (20, {"a.py": "x = 2\n"}), (10, {"a.py": "x = 3\n"})])
        base = self.sh(r, "git", "rev-parse", "HEAD~1").strip()
        self.assertEqual(compare.measure_at(r, base)[2], {"a.py": 2}, "the newest commit is after the base")

    def test_the_counts_by_kind_and_the_line_to_quote(self) -> None:
        d = self.compare(self.worked_repo())
        self.assertEqual(d["summary"]["smells"], {"before": 5, "after": 4, "change": -1})
        self.assertEqual(d["summary"]["severe"], {"before": 2, "after": 1, "change": -1})
        self.assertEqual(d["kinds"], [{"smell": "function_lines", "before": 5, "after": 4, "change": -1}])
        self.assertEqual(d["quote"], "since v1: 5 smells -> 4 (-1); past the hard limit 2 -> 1")
        self.assertEqual((d["base"], len(d["base_commit"])), ("v1", 40))
        self.assertEqual(d["not_comparable"], {"tools": [], "kinds": []})

    def test_the_smells_gone_new_smaller_and_bigger(self) -> None:
        d = self.compare(self.worked_repo())
        self.assertEqual(self.names(d["gone"]), ["fixed", "huge"])
        self.assertEqual(self.names(d["new"]), ["newcomer"])
        self.assertEqual([(r["file"], r["before"], r["after"]) for r in d["shrank"]], [("c.py", 130, 90)])
        self.assertEqual([(r["file"], r["before"], r["after"]) for r in d["grew"]], [("d.py", 70, 90)])
        self.assertEqual(d["gone"][0]["after"], None)
        self.assertEqual(d["new"][0]["before"], None)

    def test_a_renamed_file_is_matched_to_its_old_path(self) -> None:
        d = self.compare(self.worked_repo())
        listed = [r["file"] for key in ("gone", "new", "shrank", "grew") for r in d[key]]
        self.assertNotIn("pkg_b.py", listed, "the same smell in the same function is not new for being moved")
        self.assertNotIn("b.py", listed, "and the old path is not gone")
        row = next(h for h in d["hotspots"] if h["file"] == "b.py")
        self.assertEqual((row["now"], row["status"]), ("pkg_b.py", "same"))

    def test_how_the_hotspots_of_the_base_moved(self) -> None:
        d = self.compare(self.worked_repo())
        rows = {h["file"]: h for h in d["hotspots"]}
        self.assertEqual((rows["a.py"]["severe"], rows["a.py"]["status"]),
                         ({"before": 1, "after": 0}, "cleared"))
        self.assertEqual((rows["c.py"]["severe"], rows["c.py"]["hints"], rows["c.py"]["status"]),
                         ({"before": 1, "after": 0}, {"before": 0, "after": 1}, "better"))
        self.assertEqual(rows["d.py"]["status"], "same")
        self.assertEqual(len(self.compare(self.worked_repo(), "--top", "2")["hotspots"]), 2)

    def test_the_text_ends_with_the_line_to_quote(self) -> None:
        done = self.cli(self.worked_repo(), "compare", "v1", env=self.bare)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[-1], "since v1: 5 smells -> 4 (-1); past the hard limit 2 -> 1")
        self.assertTrue(lines[0].startswith("# broom compare: "))
        titles = [x[3:] for x in lines if x.startswith("## ")]
        self.assertEqual(titles, ["Smells by kind", "Gone (2)", "New (1)", "Smaller (1)", "Bigger (1)",
                                  "Hotspots of v1"])
        self.assertIn("130 -> 90", done.stdout)

    def test_an_unknown_revision_and_a_directory_that_is_no_repo_exit_1(self) -> None:
        r = self.worked_repo()
        done = self.cli(r, "compare", "nosuchrev", env=self.bare)
        self.assertEqual((done.returncode, done.stdout), (1, ""))
        self.assertIn("unknown revision 'nosuchrev'", done.stderr)
        plain = self.tmp / "plain"
        plain.mkdir()
        done = self.cli(plain, "compare", "v1", env=self.bare)
        self.assertEqual(done.returncode, 1)
        self.assertIn("not inside a git repository", done.stderr)

    def test_the_checkout_is_gone_afterwards_with_its_worktree(self) -> None:
        r = self.worked_repo()
        scratch = self.tmp / "scratch"
        scratch.mkdir()
        done = self.cli(r, "compare", "v1", env={**self.bare, "TMPDIR": str(scratch)})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(list(scratch.iterdir()), [], "no temporary directory is left")
        self.assertEqual(len(self.sh(r, "git", "worktree", "list").splitlines()), 1)

    def test_the_rows_kept_for_a_checkout_are_forgotten_with_it(self) -> None:
        tree = self.tmp / "gone"
        path = rowcache.ROWS / f"{short_hash(str(tree))}.json"
        path.parent.mkdir(parents=True)
        for f in (path, path.with_name(path.name + ".lock")):
            f.write_text("{}")
        rowcache.forget(tree)
        rowcache.forget(tree)  # nothing left is no error
        self.assertEqual(list(path.parent.iterdir()), [])

    def test_the_checkout_is_removed_when_the_measuring_fails(self) -> None:
        r = self.worked_repo()
        scratch = self.tmp / "scratch"
        scratch.mkdir()
        with mock.patch("tempfile.tempdir", str(scratch)), \
                mock.patch.object(compare, "measure", side_effect=[([], []), RuntimeError("boom")]):
            with self.assertRaises(RuntimeError):
                compare.compare(r, "v1", 10)
        self.assertEqual(list(scratch.iterdir()), [])
        self.assertEqual(len(self.sh(r, "git", "worktree", "list").splitlines()), 1)

    def test_a_tool_that_ran_in_one_measuring_only_leaves_its_kinds_out(self) -> None:
        r = self.worked_repo()

        def smell(name: str, tool: str, metric: str) -> Smell:
            return Smell(r, r / name, 1, metric, name, 120, None, tool, "block", 100, compared=False)

        before = [smell("a.js", "js", "function_lines"), smell("a.py", "python", "function_lines")]
        after = [smell("a.py", "python", "function_lines"), smell("b.js", "js", "complexity")]
        missing = "missing:oxlint (npm i -g oxlint), so TS/JS smells aren't measured"
        with mock.patch.object(compare, "measure_at", return_value=(before, [missing], {})), \
                mock.patch.object(compare, "measure", return_value=(after, [])):
            d = compare.compare(r, "v1", 10)
        self.assertEqual(d["not_comparable"], {"tools": ["js"], "kinds": ["complexity", "function_lines"]})
        self.assertEqual(d["summary"]["smells"], {"before": 1, "after": 1, "change": 0})
        self.assertTrue(d["quote"].endswith("; not comparable: complexity, function_lines"), d["quote"])
        self.assertIn(f"at v1: {missing}", d["notes"])
        self.assertEqual((d["gone"], d["new"]), ([], []), "what only one measuring found is not 'gone' or 'new'")

    def test_a_tool_missing_in_both_is_not_a_difference(self) -> None:
        notes = ["missing:ruff (brew install ruff)"]
        self.assertEqual(compare.uncomparable([], [], (notes, list(notes))), set())
        self.assertEqual(compare.uncomparable([], [], (notes, [])), {"python"})
        self.assertEqual(compare.tools_in("timeout:cargo clippy measuring smells in /x", {"clippy", "go"}), {"clippy"})
        self.assertEqual(compare.tools_in("golangci-lint failed measuring smells in /x", {"go"}), {"go"})
