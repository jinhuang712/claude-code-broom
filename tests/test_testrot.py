"""What a repo's tests lose, as a change finds it: `skipped_test`, a test marked skipped with no condition behind it, and
`untested_file`, a code file added with no test file beside it by name; and the tests that repeat one another, which the
checks on a change leave out and the whole-repo scan keeps apart. Sample code is written as lists of lines, and a skip
in two pieces where a line of it would start like one: broom reads its own tests too."""

from __future__ import annotations

import json
import os
import shutil
import time
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from gitwork import GitWork
from support import BroomCase, py_function

from broom import checkup
from broom.config import SMELL_PRESENCE
from broom.smells import find_smells

SKIP = "@unittest." + "skip"  # a decorator line in a test file, which this file must not hold itself
XFAIL = "@pytest.mark." + "xfail"
SKIP_TEST = "self." + "skipTest"
PY_BODY = ("import unittest", "", "", "class T(unittest.TestCase):", "    def test_old(self):", "        pass")


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


class SkipCase(BroomCase):
    def changed(self, rel: str, before: str, after: str, off: Sequence[str] = ()) -> List[Tuple[str, List[int]]]:
        """The (smell, added lines) of the two testrot smells that a change of file `rel` from `before` to `after` makes
        worse."""
        r = self.repo({rel: before, ".broom.json": json.dumps({"smells_off": list(off)})})
        (r / rel).write_text(after)
        found, _ = find_smells(r, [r / rel], "HEAD")
        return [(s.metric, s.added) for s in found if s.metric in ("skipped_test", "untested_file")]


class SkippedTestTest(SkipCase):
    def test_it_is_a_hint_and_an_occurrence_smell(self) -> None:
        self.assertEqual(SMELL_PRESENCE["skipped_test"], "hint")

    def test_a_skip_a_change_adds_is_found_on_the_line_it_added(self) -> None:
        after = text(*PY_BODY, "", f"    {SKIP}(\"later\")", "    def test_new(self):", "        pass")
        self.assertEqual(self.changed("tests/test_a.py", text(*PY_BODY), after), [("skipped_test", [8])])

    def test_each_languages_own_form_counts(self) -> None:
        forms: Dict[str, Tuple[str, str, List[str], List[int]]] = {
            "python decorator": ("tests/test_a.py", "x = 1", [f"{XFAIL}", "def test_a():", "    pass"], [2]),
            "python skipTest": ("tests/test_a.py", "x = 1", ["def test_a(self):", f"    {SKIP_TEST}('wip')"], [3]),
            "js it.skip": ("src/a.test.ts", "x;", ["it.skip('a', () => {});"], [2]),
            "js xit": ("src/a.test.ts", "x;", ["xit('a', () => {});"], [2]),
            "js describe.skip": ("src/a.spec.js", "x;", ["describe.skip('a', () => {});"], [2]),
            "go t.Skip": ("svc/a_test.go", "package a", ["func TestA(t *testing.T) {", '\tt.Skip("later")', "}"], [3]),
            "rust ignore": ("src/lib.rs", "fn f() {}", ["#[test]", "#[ignore]", "fn a() {}"], [3]),
            "swift XCTSkip": ("Tests/AT.swift", "import XCTest",
                              ["func testA() throws {", '    throw XCTSkip("later")', "}"], [3]),
            "swift disabled": ("Tests/AT.swift", "import XCTest", ['@Test(.disabled("later")) func a() {}'], [2]),
        }
        for name, (rel, head, rows, lines) in forms.items():
            with self.subTest(name):
                self.assertEqual(self.changed(rel, text(head), text(head, *rows)), [("skipped_test", lines)])

    def test_a_skip_that_a_condition_decides_is_not_a_test_switched_off(self) -> None:
        quiet = {
            "skipUnless": ("tests/test_a.py", [f"{SKIP}Unless(shutil.which('x'), 'x missing')", "def test_a(): pass"]),
            "skipIf": ("tests/test_a.py", [f"{SKIP}If(sys.platform == 'win32', 'posix only')", "def test_a(): pass"]),
            "pytest skipif": ("tests/test_a.py", ["@pytest.mark.skipif(not HAS_X, reason='x')", "def test_a(): pass"]),
            "an if above": ("tests/test_a.py", ["def test_a(self):", "    if not shutil.which('x'):",
                                                f"        {SKIP_TEST}('x missing')"]),
            "an if on the line": ("svc/a_test.go", ["func TestA(t *testing.T) {",
                                                    '\tif testing.Short() { t.Skip("short") }', "}"]),
            "go guard": ("svc/a_test.go", ["func TestA(t *testing.T) {", "\tif _, err := exec.LookPath(\"x\"); err != nil {",
                                           '\t\tt.Skip("x missing")', "\t}", "}"]),
            "XCTSkipUnless": ("Tests/AT.swift", ["func testA() throws {", "    try XCTSkipUnless(ok)", "}"]),
        }
        for name, (rel, rows) in quiet.items():
            with self.subTest(name):
                self.assertEqual(self.changed(rel, "x = 1\n", text("x = 1", *rows)), [])

    def test_a_skip_that_was_there_stays_quiet_and_so_does_one_that_moved(self) -> None:
        old = text(*PY_BODY, "", f"    {SKIP}(\"later\")", "    def test_skipped(self):", "        pass")
        self.assertEqual(self.changed("tests/test_a.py", old, old.replace("pass", "pass  # edited")), [])
        moved = old.replace("class T", "VALUE = 1\n\n\nclass T")
        self.assertEqual(self.changed("tests/test_a.py", old, moved), [], "a skip that only moved down is old")

    def test_a_second_skip_in_the_file_counts_when_the_count_rises(self) -> None:
        one = text(*PY_BODY, "", f"    {SKIP}(\"a\")", "    def test_a(self):", "        pass")
        two = one + text("", f"    {SKIP}(\"b\")", "    def test_b(self):", "        pass")
        self.assertEqual(self.changed("tests/test_a.py", one, two), [("skipped_test", [12])])

    def test_a_skip_outside_a_test_file_is_not_a_skipped_test(self) -> None:
        self.assertEqual(self.changed("lib/a.py", "x = 1\n", text("x = 1", f"{SKIP}(\"later\")", "def f(): pass")), [])
        self.assertEqual(self.changed("lib/a.ts", "x;\n", text("x;", "it.skip('a', () => {});")), [])

    def test_smells_off_turns_it_off(self) -> None:
        after = text(*PY_BODY, "", f"    {SKIP}(\"later\")", "    def test_new(self):", "        pass")
        self.assertEqual(self.changed("tests/test_a.py", text(*PY_BODY), after, off=["skipped_test"]), [])

    def test_it_needs_no_tool(self) -> None:
        after = text(*PY_BODY, "", f"    {SKIP}(\"later\")", "    def test_new(self):", "        pass")
        r = self.repo({"tests/test_a.py": text(*PY_BODY)})
        (r / "tests/test_a.py").write_text(after)
        done = self.cli(r, "smells", "--base", "HEAD", "--json", env=self.fake_path())
        self.assertEqual(done.returncode, 0, done.stderr)
        smells = json.loads(done.stdout)["smells"]
        self.assertEqual([(s["smell"], s["level"], s["line"]) for s in smells], [("skipped_test", "hint", 8)])
        self.assertIn("skipped or disabled test(s)", smells[0]["text"])


def lines_of_code(n: int, name: str = "X") -> str:
    """A Python file of `n` non-blank lines."""
    return "".join(f"{name}{i} = {i}\n" for i in range(n))


class UntestedFileTest(BroomCase):
    def added(self, files: Dict[str, str], existing: Optional[Dict[str, str]] = None, off: Sequence[str] = (),
              base: Optional[str] = "HEAD") -> List[Tuple[str, List[int]]]:
        """The (smell, added lines) of `untested_file` that adding `files` to a repo holding `existing` makes."""
        r = self.repo({"README.md": "x\n", **(existing or {}), ".broom.json": json.dumps({"smells_off": list(off)})})
        for rel, body in files.items():
            (r / rel).parent.mkdir(parents=True, exist_ok=True)
            (r / rel).write_text(body)
        found, _ = find_smells(r, [r / rel for rel in files], base)
        return [(s.metric, s.added) for s in found if s.metric == "untested_file"]

    def test_it_is_a_hint_and_an_occurrence_smell(self) -> None:
        self.assertEqual(SMELL_PRESENCE["untested_file"], "hint")

    def test_a_code_file_of_30_lines_added_with_no_test_beside_it_is_found(self) -> None:
        self.assertEqual(self.added({"pkg/fresh.py": lines_of_code(30)}), [("untested_file", [1])])
        self.assertEqual(self.added({"pkg/fresh.py": lines_of_code(29)}), [], "one line short of it")

    def test_blank_lines_do_not_count(self) -> None:
        self.assertEqual(self.added({"pkg/fresh.py": lines_of_code(29).replace("\n", "\n\n")}), [])

    def test_a_test_file_named_for_it_anywhere_in_the_repo_settles_it(self) -> None:
        self.assertEqual(self.added({"pkg/fresh.py": lines_of_code(40)}, {"tests/test_fresh.py": "x = 1\n"}), [])
        self.assertEqual(self.added({"pkg/fresh.py": lines_of_code(40)}, {"elsewhere/fresh_test.py": "x = 1\n"}), [])
        self.assertEqual(self.added({"pkg/fresh.py": lines_of_code(40), "tests/test_fresh.py": "x = 1\n"}), [],
                         "a test added in the same change is beside it")

    def test_the_pairing_goes_by_each_languages_name_form(self) -> None:
        go = "package a\n" + "".join(f"var V{i} = {i}\n" for i in range(40))
        ts = "".join(f"export const v{i} = {i};\n" for i in range(40))
        swift = "".join(f"let v{i} = {i}\n" for i in range(40))
        self.assertEqual(self.added({"svc/util.go": go}), [("untested_file", [1])])
        self.assertEqual(self.added({"svc/util.go": go}, {"svc/util_test.go": "package a\n"}), [])
        self.assertEqual(self.added({"src/lib.ts": ts}), [("untested_file", [1])])
        self.assertEqual(self.added({"src/lib.ts": ts}, {"src/lib.spec.ts": "x;\n"}), [])
        self.assertEqual(self.added({"Sources/Thing.swift": swift}), [("untested_file", [1])])
        self.assertEqual(self.added({"Sources/Thing.swift": swift}, {"Tests/ThingTests.swift": "x\n"}), [])

    def test_languages_the_pairing_does_not_know_get_none(self) -> None:
        rust = "".join(f"const V{i}: u32 = {i};\n" for i in range(40))
        css = "".join(f".c{i} {{ color: red; }}\n" for i in range(40))
        self.assertEqual(self.added({"src/lib.rs": rust, "web/site.css": css}), [])

    def test_a_test_a_package_marker_and_old_files_are_not_found(self) -> None:
        body = lines_of_code(40)
        self.assertEqual(self.added({"tests/test_x.py": body, "pkg/__init__.py": body, "pkg/conftest.py": body}), [])
        self.assertEqual(self.added({"pkg/old.py": lines_of_code(60)}, {"pkg/old.py": lines_of_code(5)}), [],
                         "a file that grew was not added")

    def test_a_moved_file_is_not_an_added_one(self) -> None:
        r = self.repo({"pkg/old.py": lines_of_code(40)})
        self.sh(r, "git", "mv", "pkg/old.py", "pkg/moved.py")
        found, _ = find_smells(r, [r / "pkg/moved.py"], "HEAD")
        self.assertEqual([s.metric for s in found if s.metric == "untested_file"], [])

    def test_a_sweep_of_the_whole_repo_finds_none_since_no_change_added_a_file(self) -> None:
        self.assertEqual(self.added({"pkg/fresh.py": lines_of_code(40)}, base=None), [])

    def test_smells_off_turns_it_off(self) -> None:
        self.assertEqual(self.added({"pkg/fresh.py": lines_of_code(40)}, off=["untested_file"]), [])

    def test_it_needs_no_tool_and_the_hint_carries_the_fix(self) -> None:
        r = self.repo({"README.md": "x\n"})
        (r / "pkg").mkdir()
        (r / "pkg/fresh.py").write_text(lines_of_code(40))
        done = self.cli(r, "smells", "--base", "HEAD", "--json", env=self.fake_path())
        self.assertEqual(done.returncode, 0, done.stderr)
        smells = json.loads(done.stdout)["smells"]
        self.assertEqual([(s["file"], s["smell"], s["level"]) for s in smells], [("pkg/fresh.py", "untested_file", "hint")])
        self.assertIn("no test file beside it by name", smells[0]["text"])
        self.assertIn("test_name.py", self.cli(r, "fixes", "untested_file").stdout)


HAS_JSCPD = shutil.which("jscpd") is not None
BODY = py_function("one", 40).split("\n", 1)[1]  # 39 lines: the same text in two test files is a clone
TELL = "At a natural point tell the user; don't interrupt their task."


def test_with_body(name: str) -> str:
    """A test file whose one test has `BODY`."""
    return f"def test_{name}(x):\n{BODY}"


@unittest.skipUnless(HAS_JSCPD, "jscpd missing")
class DuplicateTestsTest(GitWork):
    def two_copies(self) -> Path:
        """A repo whose test_a.py and test_b.py repeat one test, the older file test_a.py."""
        r = self.repo({"tests/test_a.py": test_with_body("a"), "tests/test_b.py": test_with_body("b"),
                       "pkg/code.py": "VALUE = 1\n"})
        old = time.time() - 3600
        os.utime(r / "tests/test_a.py", (old, old))
        return r

    def test_a_scan_keeps_them_apart_from_the_smells(self) -> None:
        r = self.two_copies()
        found, notes = find_smells(r, [r / "tests/test_a.py", r / "tests/test_b.py"], "HEAD")
        self.assertEqual(notes, [])
        self.assertEqual([s for s in found if s.metric == "duplicate_lines"], [], "the checks on a change leave them out")
        (clone,) = found.duplicate_tests
        self.assertEqual({clone.rel, clone.other}, {"tests/test_a.py", "tests/test_b.py"})
        self.assertGreater(clone.lines, 30)

    def test_the_whole_repo_scan_lists_each_with_both_places_and_the_lines_shared_the_largest_first(self) -> None:
        r = self.two_copies()
        (r / "tests/test_c.py").write_text(test_with_body("c").replace("+=", "-=").replace("x -= 5", "x -= 6"))
        (r / "tests/test_d.py").write_text((r / "tests/test_c.py").read_text().replace("test_c", "test_d"))
        found, _ = find_smells(r, [r / "tests/test_a.py", r / "tests/test_b.py", r / "tests/test_c.py",
                                   r / "tests/test_d.py"], None)
        pairs = [{c.rel, c.other} for c in found.duplicate_tests]
        self.assertIn({"tests/test_a.py", "tests/test_b.py"}, pairs)
        self.assertIn({"tests/test_c.py", "tests/test_d.py"}, pairs)
        self.assertEqual([c.lines for c in found.duplicate_tests], sorted((c.lines for c in found.duplicate_tests),
                                                                         reverse=True))

    def test_a_copy_of_code_in_a_test_is_a_smell_and_not_a_duplicate_test(self) -> None:
        r = self.repo({"code.py": "def one(x):\n" + BODY, "tests/test_a.py": test_with_body("a")})
        found, _ = find_smells(r, [r / "code.py", r / "tests/test_a.py"], None)
        self.assertEqual(found.duplicate_tests, [])
        self.assertEqual([s.metric for s in found if s.metric == "duplicate_lines"], ["duplicate_lines"])

    def test_the_scan_of_some_files_keeps_the_clones_with_a_side_among_them(self) -> None:
        r = self.two_copies()
        mine, _ = find_smells(r, [r / "tests/test_a.py"], None)
        self.assertEqual(len(mine.duplicate_tests), 1)
        other, _ = find_smells(r, [r / "pkg/code.py"], None)
        self.assertEqual(other.duplicate_tests, [])

    def test_small_clones_generated_and_legacy_tests_are_left_out(self) -> None:
        short = "def test_s(x):\n" + "".join(f"    x += {i}\n" for i in range(6)) + "    return x\n"
        r = self.repo({"tests/test_s1.py": short, "tests/test_s2.py": short.replace("test_s", "test_t")})
        self.assertEqual(find_smells(r, [r / "tests/test_s1.py"], None)[0].duplicate_tests, [])
        legacy = self.repo({"tests/test_a.py": test_with_body("a"), "tests/test_b.py": test_with_body("b"),
                            ".broom.json": json.dumps({"legacy": ["tests/test_b.py"]})})
        self.assertEqual(find_smells(legacy, [legacy / "tests/test_a.py"], None)[0].duplicate_tests, [])
        header = "# DO NOT EDIT\n"
        gen = self.repo({"tests/test_a.py": header + test_with_body("a"), "tests/test_b.py": test_with_body("b")})
        self.assertEqual(find_smells(gen, [gen / "tests/test_b.py"], None)[0].duplicate_tests, [])

    def test_smells_off_duplicate_lines_leaves_the_scan_without_them(self) -> None:
        r = self.repo({"tests/test_a.py": test_with_body("a"), "tests/test_b.py": test_with_body("b"),
                       ".broom.json": json.dumps({"smells_off": ["duplicate_lines"]})})
        self.assertEqual(find_smells(r, [r / "tests/test_a.py"], None)[0].duplicate_tests, [])

    def scan(self, r: Path, session: str) -> str:
        """What the async session scan tells Claude in `session`, with every tool the machine has."""
        out = self.session(r, session, self.env, "session-scan")
        return out.get("hookSpecificOutput", {}).get("additionalContext", "")

    def test_the_check_up_counts_them_on_the_newer_side_and_tells_when_they_grow(self) -> None:
        r = self.repo({"tests/test_a.py": test_with_body("a"), "pkg/code.py": "VALUE = 1\n"})
        self.assertEqual(self.scan(r, "s1"), "")
        counters = json.loads(checkup.record_path(r).read_text())["counters"]
        self.assertEqual(counters["duplicate_tests"], {}, "none yet, and counted")
        self.commit_all(r, {"tests/test_b.py": test_with_body("b")})
        note = self.scan(r, "s2")
        self.assertIn("duplicate test blocks 0 -> 1 (tests/test_b.py)", note)
        self.assertEqual(self.scan(r, "s3"), "", "told once")
        self.commit_all(r, {"tests/test_b.py": "X = 1\n"})
        self.assertEqual(self.scan(r, "s4"), "", "a number that fell says nothing")
        self.assertEqual(json.loads(checkup.record_path(r).read_text())["counters"]["duplicate_tests"], {})

    def test_the_diagnosis_lists_them_in_a_section_and_in_the_json(self) -> None:
        r = self.two_copies()
        data = json.loads(self.cli(r, "diagnose", "--json").stdout)
        (row,) = data["duplicate_tests"]
        self.assertEqual({row["file"], row["other"]}, {"tests/test_a.py", "tests/test_b.py"})
        self.assertEqual((row["line"], row["other_line"]), (1, 1))
        self.assertGreater(row["lines"], 30)
        counter = {c["counter"]: c for c in data["checkup"]["counters"]}["duplicate_tests"]
        self.assertEqual((counter["label"], counter["now"]), ("duplicate test blocks", 1))
        text = self.cli(r, "diagnose").stdout
        section = text.split("## Duplicate tests\n")[1].split("\n\n## ")[0].splitlines()
        self.assertIn("1 place(s) where tests repeat one another", section[0])
        self.assertRegex(section[1], r"^  where\s+also at\s+lines$")
        self.assertRegex(section[2], r"^  tests/test_[ab]\.py:1\s+tests/test_[ab]\.py:1\s+\d+$")
        self.assertLess(text.index("## Check-up"), text.index("## Duplicate tests"))
        self.assertLess(text.index("## Duplicate tests"), text.index("## Size"))


class DuplicateTestsWithoutTheToolTest(GitWork):
    def test_without_jscpd_nothing_is_counted_and_the_diagnosis_says_it_was_not_measured(self) -> None:
        bare = self.fake_path()
        r = self.repo({"tests/test_a.py": test_with_body("a"), "tests/test_b.py": test_with_body("b")})
        out = self.session(r, "s1", bare, "session-scan")
        self.assertEqual(out, {})
        self.assertNotIn("duplicate_tests", json.loads(checkup.record_path(r).read_text())["counters"])
        data = json.loads(self.cli(r, "diagnose", "--json", env=bare).stdout)
        self.assertEqual(data["duplicate_tests"], [])
        row = {c["counter"]: c for c in data["checkup"]["counters"]}["duplicate_tests"]
        self.assertIsNone(row["now"])
        text = self.cli(r, "diagnose", env=bare).stdout
        self.assertIn("## Duplicate tests\n  not measured: jscpd is missing", text)
        self.assertRegex(text, r"\n  duplicate test blocks\s+-\s+-\s+not measured\n")
