"""broom stats: the numbers of each section on small known repos, a path that narrows, the shape of the JSON, a marker
in a string, and the exit code outside a repo. Sample code is written as lists of lines so that a line of it never
starts a line of this file: broom reads its own tests too."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from support import BroomCase

from broom import statscan, stats, statsview

# Written in two pieces: this file would otherwise hold suppressions itself.
NOQA = "# no" + "qa: E501"
TYPE_IGNORE = "# type" + ": ignore[assignment]"


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


class StatsCase(BroomCase):
    def report(self, r: Path, *paths: str, top: int = 10, last: int = 500) -> dict:
        return stats.report(r, [r / p for p in paths], top, last)

    def json(self, r: Path, *args: str) -> dict:
        done = self.cli(r, "stats", "--json", *args)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def commit_all(self, r: Path, files: dict, date: str = "") -> None:
        """Write `files` and commit them, at `date` when it is given."""
        for name, body in files.items():
            (r / name).parent.mkdir(parents=True, exist_ok=True)
            (r / name).write_text(body)
        self.sh(r, "git", "add", "-A")
        dates = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}
        done = subprocess.run(["git", "commit", "-qm", "c"], cwd=r, env={**self.env, **dates}, capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr)


class SizeTest(StatsCase):
    FILES = {
        "src/a.py": text("x = 1", "", "y = 2"),
        "src/b.ts": text("export const a = 1;", "export const b = 2;", "", "export const c = 3;"),
        "tests/test_a.py": text("def test_a():", "    pass"),
        "main.go": text("package main", "", "func main() {}"),
        "README.md": text("not code"),
        "node_modules/pkg/index.js": text("module.exports = 1;"),  # a dependency
        "gen/out.py": text("# DO NOT EDIT", "x = 1"),  # generated
        "old/legacy.py": text("x = 1"),  # excluded by .broom.json
        ".broom.json": '{"exclude": ["old/*"], "smells_off": ["dead_code"]}',
    }

    def test_lines_by_language_and_folder_with_tests_apart(self) -> None:
        d = self.report(self.repo(self.FILES))
        self.assertEqual(d["files"], 4, "dependencies, generated code and excluded paths are not read")
        size = d["size"]
        self.assertEqual(size["total"], {"files": 3, "lines": 7, "test_files": 1, "test_lines": 2})
        self.assertEqual([(r["language"], r["files"], r["lines"], r["test_files"], r["test_lines"])
                          for r in size["languages"]],
                         [("py", 1, 2, 1, 2), ("js", 1, 3, 0, 0), ("go", 1, 2, 0, 0)])
        self.assertEqual([(r["folder"], r["files"], r["lines"], r["test_lines"]) for r in size["folders"]],
                         [("src", 2, 5, 0), (".", 1, 2, 0), ("tests", 0, 0, 2)])
        self.assertIsNone(size["note"])

    def test_the_longest_files_and_the_top_cut(self) -> None:
        size = self.report(self.repo(self.FILES), top=2)["size"]
        self.assertEqual(size["longest"], [{"file": "src/b.ts", "lines": 3, "test": False},
                                           {"file": "main.go", "lines": 2, "test": False}])
        self.assertEqual((len(size["folders"]), size["more_folders"]), (2, 1))

    def test_a_path_narrows_every_count(self) -> None:
        d = self.report(self.repo(self.FILES), "src")
        self.assertEqual((d["paths"], d["files"]), (["src"], 2))
        self.assertEqual(d["size"]["total"]["lines"], 5)
        self.assertEqual([r["folder"] for r in d["size"]["folders"]], ["src"])


class TestCountTest(StatsCase):
    FILES = {
        "tests/test_a.py": text(
            "import unittest", "", "class T(unittest.TestCase):", "    def test_one(self):", "        pass", "",
            '    @unittest.skip("later")', "    def test_two(self):", "        self." + 'skipTest("x")', "",
            '    @unittest.skipUnless(True, "no")', "    async def test_three(self):", "        pass", "",
            "@pytest.mark.xfail", "def test_four():", "    pass"),
        "src/b.test.ts": text(
            "describe('b', () => {", "  it('one', () => {});", "  test('two', () => {});",
            "  it.skip('three', () => {});", "  xit('four', () => {});", "  xdescribe('group', () => {});",
            "  test.each([1])('five', () => {});", "  expect(re.test(x)).toBe(true);", "});"),
        "svc/a_test.go": text("package a", "", "func TestOne(t *testing.T) {", '\tt.Skip("later")', "}", "",
                              "func TestTwo(t *testing.T) {}", "", "func helper() {}"),
        "src/lib.rs": text("fn f() {}", "", "#[cfg(test)]", "mod tests {", "    #[test]", "    fn one() {}", "",
                           "    #[test]", "    #[ignore]", "    fn two() {}", "}"),
        "Tests/FooTests.swift": text(
            "import XCTest", "", "final class FooTests: XCTestCase {", "    func testOne() throws {",
            "        try XCTSkipIf(true)", "    }", "", "    func testTwo() {}", "}", "", "@Test func three() {}", "",
            '@Test(.disabled("x")) func four() {}'),
    }

    def test_cases_and_skipped_tests_by_each_languages_own_form(self) -> None:
        t = self.report(self.repo(self.FILES))["tests"]
        self.assertEqual([(r["language"], r["files"], r["cases"], r["skipped"]) for r in t["languages"]],
                         [("go", 1, 2, 1), ("js", 1, 5, 3), ("py", 1, 4, 4), ("rust", 0, 2, 1), ("swift", 1, 4, 2)])
        self.assertEqual((t["files"], t["cases"], t["skipped"]), (4, 17, 11))
        self.assertEqual(t["skipped_files"][:2], [{"file": "tests/test_a.py", "count": 4},
                                                  {"file": "src/b.test.ts", "count": 3}])

    def test_skipped_tests_are_a_number_in_rot_too(self) -> None:
        d = self.report(self.repo(self.FILES), top=1)
        self.assertEqual(d["rot"]["skipped_tests"], 11)
        self.assertEqual(len(d["tests"]["skipped_files"]), 1)

    def test_code_files_with_no_test_file_by_name(self) -> None:
        r = self.repo({
            "src/a.py": text("x = 1"), "tests/test_a.py": text("def test_a():", "    pass"),  # test_foo.py
            "src/x.py": text("x = 1"), "src/x_test.py": text("def test_x():", "    pass"),  # foo_test.py
            "src/c.py": text("a = 1", "b = 2", "c = 3"), "src/__init__.py": text("x = 1"),
            "svc/a.go": text("package a"), "svc/a_test.go": text("package a"),
            "svc/b.go": text("package b", "var x = 1"),
            "src/b.ts": text("export {};"), "src/b.test.ts": text("it('b', () => {});"),
            "src/e.ts": text("export {};"), "src/e.spec.ts": text("it('e', () => {});"),
            "src/d.tsx": text("export {};"),
            "Sources/Foo.swift": text("struct Foo {}"), "Tests/FooTests.swift": text("final class FooTests {}"),
            "Sources/Bar.swift": text("struct Bar {}"),
            "src/lib.rs": text("fn f() {}"),  # Rust names no test file
        })
        u = self.report(r, top=3)["tests"]["untested"]
        self.assertEqual((u["count"], u["of"]), (4, 10))
        self.assertEqual(u["largest"], [{"file": "src/c.py", "lines": 3}, {"file": "svc/b.go", "lines": 2},
                                        {"file": "Sources/Bar.swift", "lines": 1}])


class RotTest(StatsCase):
    def old_repo(self) -> Path:
        r = self.repo({
            "a.py": text("x = 1  " + NOQA, "y = 2  " + TYPE_IGNORE, 'z = "no' + 'qa"', "w = 3"),
            "b.ts": text("// eslint" + "-disable-next-line no-console", "foo();", "// @ts" + "-ignore"),
            "c.rs": text("#[al" + "low(dead_code)]", "fn f() {}"),
            "t.py": text("x = 1  # TODO: first", 's = "TODO: in a string"', "# FIXME second", '"""',
                         "# HACK inside a docstring", '"""', "y = 2  # XXX third", 't = "# TODO still a string"'),
            "u.ts": text("const a = 1; // TODO: a", "/*", " * FIXME in a block", " */",
                         'const b = "// TODO not a comment";', "const c = `TODO template`;"),
        })
        return r

    def test_suppressions_by_kind_and_a_marker_in_a_string_is_none(self) -> None:
        s = self.report(self.old_repo())["rot"]["suppressions"]
        self.assertEqual(s["total"], 5, 'z = "noqa" in a.py is a string')
        self.assertEqual(s["kinds"], {"noqa": 1, "type: ignore": 1, "eslint-disable": 1, "@ts-ignore": 1, "allow": 1})
        self.assertEqual([(f["file"], f["count"]) for f in s["files"]], [("a.py", 2), ("b.ts", 2), ("c.rs", 1)])

    def test_todo_comments_count_in_comments_and_not_in_strings(self) -> None:
        t = self.report(self.old_repo())["rot"]["todos"]
        self.assertEqual(t["total"], 5)
        self.assertEqual([(f["file"], f["count"]) for f in t["files"]], [("t.py", 3), ("u.ts", 2)])

    def test_a_todo_is_a_marker_and_not_a_word_in_a_comments_prose(self) -> None:
        marked = ["# TODO: one", "x = 1  # FIXME later", "# see below. HACK(dev): three", "# XXX"]
        prose = ["# a TODO in the list stays open", "# TODO.md holds the open questions", "# the FIXME tag is for bugs"]
        r = self.repo({"a.py": text(*marked, *prose),
                       "b.ts": text("/*", " * TODO: in a block", " * every TODO has an owner", " */", "export {};")})
        t = self.report(r)["rot"]["todos"]
        self.assertEqual([(f["file"], f["count"]) for f in t["files"]], [("a.py", 4), ("b.ts", 1)])

    def test_todos_are_counted_without_an_age(self) -> None:
        d = self.report(self.old_repo(), top=6)
        t = d["rot"]["todos"]
        self.assertEqual(set(t), {"total", "files"})
        self.assertEqual(t["total"], 5)
        text = statsview.render(d)
        self.assertIn("\n  5 TODO, FIXME, HACK or XXX comments\n", text)
        self.assertNotIn("blame", text)


class HistoryTest(StatsCase):
    def busy_repo(self) -> Path:
        r = self.repo({"a.py": "1\n", "b.py": "1\n", "c.py": "1\n", "README.md": "x\n"})
        self.commit_all(r, {"a.py": "2\n", "b.py": "2\n"})
        self.commit_all(r, {"a.py": "3\n"})
        self.commit_all(r, {"a.py": "4\n", "b.py": "4\n", **{f"data/n{i}.txt": "x\n" for i in range(31)}})
        return r

    def test_commits_per_file_and_the_files_that_changed_together(self) -> None:
        h = self.report(self.busy_repo())["history"]
        self.assertEqual((h["commits"], h["last_commits"], h["note"]), (4, 500, None))
        self.assertEqual(h["files"], [{"file": "a.py", "commits": 4}, {"file": "b.py", "commits": 3},
                                      {"file": "c.py", "commits": 1}])
        self.assertEqual(h["pairs"], [{"files": ["a.py", "b.py"], "commits": 2},
                                      {"files": ["a.py", "c.py"], "commits": 1},
                                      {"files": ["b.py", "c.py"], "commits": 1}],
                         "the commit of 33 files counts for no pair")

    def test_a_path_narrows_the_pairs_to_its_files(self) -> None:
        r = self.repo({"x/a.py": "1\n", "x/b.py": "1\n", "y/c.py": "1\n"})
        h = self.report(r, "x", top=1)["history"]
        self.assertEqual(h["files"], [{"file": "x/a.py", "commits": 1}])
        self.assertEqual(h["pairs"], [{"files": ["x/a.py", "x/b.py"], "commits": 1}])

    def test_only_the_last_commits_are_counted_and_none_says_so(self) -> None:
        r = self.repo({"a.py": "1\n", "b.py": "1\n"})
        self.commit_all(r, {"a.py": "2\n"})
        h = self.report(r, last=1)["history"]
        self.assertEqual((h["commits"], h["files"], h["last_commits"]), (1, [{"file": "a.py", "commits": 1}], 1))
        self.assertEqual(self.report(r)["history"]["commits"], 2)
        self.assertEqual(self.report(r, last=0)["history"]["note"], "no commits to count")

    def test_a_repo_without_a_commit_has_no_history_to_count(self) -> None:
        r = self.tmp / "fresh"
        r.mkdir()
        self.sh(r, "git", "init", "-q")
        (r / "a.py").write_text("x = 1\n")
        d = self.report(r)
        self.assertEqual(d["files"], 1)
        self.assertTrue(d["history"]["note"].startswith("no history yet"), d["history"])


class ScanTest(StatsCase):
    def test_a_marker_or_a_todo_word_in_a_string_is_none(self) -> None:
        f = statscan.scan("a.py", "py", text('x = "no' + 'qa"', 'y = "# TODO"', '"""', "# FIXME", '"""', "# HACK"))
        self.assertEqual((f.suppressions, f.todos), ([], [6]))

    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_rust_and_css_tests_and_comments_come_from_the_tree(self) -> None:
        r = self.repo({
            "src/a.rs": text("#[test]", "fn a() {}", "#[tokio::test]", '#[ignore = "slow"]', "async fn b() {}",
                             '#[cfg_attr(not(feature = "x"), ignore)]', "#[test]", "fn c() {}", "// TODO: fix",
                             'fn d() { let s = "// TODO: no #[test] #[ignore]"; }'),
            "a.css": text("/* one", "HACK: two */", 'a { content: "/* TODO: no */" }'),
            "b.scss": text("// FIXME: three", ".a { .b { color: red } }")})
        facts = {f.rel: f for f in stats.collect(r, [])}
        rust = facts["src/a.rs"]
        self.assertEqual((rust.cases, rust.skipped, rust.todos), (3, 2, [9]))
        self.assertEqual((facts["a.css"].todos, facts["b.scss"].todos), ([2], [1]))

    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_go_and_ts_comments_come_from_the_tree_and_a_marker_in_a_string_is_none(self) -> None:
        r = self.repo({
            "a.ts": text("/* one", "TODO two */ x()", "y() // XXX three", "`TODO", "four` + 1", 'z("// TODO: no");'),
            "a_test.go": text("package a", "// TODO: go", "func TestA(t *testing.T) {", '\ts := "// TODO: no" + `',
                              "TODO: raw", "` // no" + "lint", '\tt.Log("t.Skip()")', "}")})
        facts = {f.rel: f for f in stats.collect(r, [])}
        self.assertEqual(facts["a.ts"].todos, [2, 3])
        go = facts["a_test.go"]
        self.assertEqual((go.todos, go.suppressions, go.cases, go.skipped), ([2], ["nolint"], 1, 0))

    def test_without_ast_grep_a_go_or_ts_file_is_unread_and_a_note_says_so(self) -> None:
        r = self.repo({"a.ts": text("// TODO: one"), "b.py": text("# TODO: two")})
        with mock.patch.object(shutil, "which", return_value=None):
            d = self.report(r)
            facts = {f.rel: f.read for f in stats.collect(r, [])}
        self.assertEqual(facts, {"a.ts": False, "b.py": True})
        self.assertEqual(d["rot"]["todos"]["total"], 1)
        self.assertIn("ast-grep", d["rot"]["note"])


class CommandTest(StatsCase):
    SECTIONS = {
        "size": {"total", "languages", "folders", "more_folders", "longest", "note"},
        "tests": {"files", "with_cases", "cases", "skipped", "languages", "skipped_files", "untested", "coverage",
                  "note"},
        "rot": {"suppressions", "todos", "skipped_tests", "note"},
        "history": {"last_commits", "commits", "files", "pairs", "note"},
    }

    def test_json_is_one_object_with_four_sections(self) -> None:
        r = self.repo({"src/a.py": "x = 1\n", "src/b.py": "y = 2\n"})
        d = self.json(r)
        self.assertEqual(set(d), {"repo", "paths", "files", "last_commits", "size", "tests", "rot", "history"})
        self.assertEqual({k: set(d[k]) for k in self.SECTIONS}, self.SECTIONS)
        self.assertEqual((d["repo"], d["paths"], d["files"], d["last_commits"]), (str(r), [], 2, 500))
        self.assertEqual(self.json(r, "--commits", "7", "--top", "1")["last_commits"], 7)

    def test_text_has_a_short_heading_per_section(self) -> None:
        r = self.repo({"src/a.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    pass\n"})
        done = self.cli(r, "stats")
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        headings = [row for row in done.stdout.splitlines() if row and not row.startswith(" ")]
        self.assertEqual([h.split(" (")[0] for h in headings[1:]], ["Size", "Tests", "Rot", "History"])
        self.assertIn("goes by file name", done.stdout)
        self.assertIn("2 code files read", headings[0])

    def test_a_language_reads_by_its_name_and_the_json_keeps_the_short_one(self) -> None:
        r = self.repo({"src/a.ts": "export const a = 1;\n", "src/b.py": "x = 1\n"})
        out = self.cli(r, "stats").stdout
        self.assertRegex(out, r"\n  TS/JS\s+1\s+1\s+0\s+0\n")
        self.assertRegex(out, r"\n  Python\s+1\s+1\s+0\s+0\n")
        self.assertEqual({row["language"] for row in self.json(r)["size"]["languages"]}, {"js", "py"})

    def test_a_helper_under_a_test_folder_is_a_test_file_with_no_test_cases(self) -> None:
        r = self.repo({"src/a.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    pass\n",
                       "tests/helpers.py": "def make():\n    return 1\n"})
        tests = self.json(r)["tests"]
        self.assertEqual((tests["files"], tests["with_cases"], tests["cases"]), (2, 1, 1))
        self.assertIn("  2 test files (1 of them hold test cases), 1 test cases, 0 skipped", self.cli(r, "stats").stdout)
        (r / "tests/helpers.py").unlink()
        self.assertIn("  1 test files, 1 test cases, 0 skipped", self.cli(r, "stats").stdout)

    def test_a_path_narrows(self) -> None:
        r = self.repo({"src/a.py": "x = 1\n", "lib/b.py": "y = 2\nz = 3\n"})
        d = self.json(r, "lib")
        self.assertEqual((d["paths"], d["files"], d["size"]["total"]["lines"]), (["lib"], 1, 2))
        self.assertIn("narrowed to lib", self.cli(r, "stats", "lib").stdout)

    def test_a_path_with_no_code_files_says_what_is_missing(self) -> None:
        r = self.repo({"src/a.py": "x = 1\n", "docs/readme.md": "hi\n"})
        d = self.json(r, "docs")
        self.assertEqual(d["files"], 0)
        for section in self.SECTIONS:
            self.assertEqual(d[section]["note"], "no code files under docs", section)
        done = self.cli(r, "stats", "docs")
        self.assertEqual(done.returncode, 0)
        self.assertIn("note: no code files under docs", done.stdout)

    def test_outside_a_git_repo_it_exits_1(self) -> None:
        plain = self.tmp / "plain"
        plain.mkdir()
        done = self.cli(plain, "stats")
        self.assertEqual(done.returncode, 1)
        self.assertIn("not inside a git repository", done.stderr)
