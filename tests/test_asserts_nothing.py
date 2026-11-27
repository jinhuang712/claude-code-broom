"""A test that asserts nothing passes whatever the code does: the extreme of `broad_test_asserts`. Sure in TS/JS and Go,
a hint; a guess in Python, Rust and Swift, where a helper of the test's own may assert, so a nit."""

from __future__ import annotations

import shutil
import unittest
from typing import Dict, List, Tuple

from support import BroomCase

from broom.config import NIT
from broom.smell import ASSERTS_NOTHING, Smell
from broom.smells import find_smells

METRIC = "broad_test_asserts"


def rows(*lines: str) -> str:
    """A file's text from its lines."""
    return "\n".join(lines) + "\n"


GO_HEAD = ("package a", "", 'import "testing"', "")
# Per language: the tool it needs, the test file, a test that asserts nothing, one that asserts, and the level.
SAMPLES: Dict[str, Tuple[str, str, str, str, str]] = {
    "ts": ("oxlint", "src/a.test.ts", rows('test("t", () => {', "  const x = 1;", "});"),
           rows('test("t", () => {', "  expect(f()).toBe(1);", "});"), "hint"),
    "go": ("ast-grep", "a_test.go", rows(*GO_HEAD, "func TestA(t *testing.T) {", "\tx := 1", "\t_ = x", "}"),
           rows(*GO_HEAD, "func TestA(t *testing.T) {", "\tif f() != 1 {", '\t\tt.Errorf("bad")', "\t}", "}"),
           "hint"),
    "py": ("python3", "tests/test_a.py", rows("def test_a():", "    x = 1"),
           rows("def test_a():", "    assert f() == 1"), NIT),
    "rust": ("ast-grep", "tests/it.rs", rows("#[test]", "fn quiet() {", "    let _ = f();", "}"),
             rows("#[test]", "fn loud() {", "    assert_eq!(f(), 1);", "}"), NIT),
    "swift": ("swiftc", "Tests/ATests.swift",
              rows("import XCTest", "", "final class ATests: XCTestCase {", "    func testA() {", "        let x = 1",
                   "    }", "}"),
              rows("import XCTest", "", "final class ATests: XCTestCase {", "    func testA() {",
                   "        XCTAssertEqual(f(), 1)", "    }", "}"), NIT),
}


class AssertsNothingTest(BroomCase):
    def found(self, rel: str, text: str) -> List[Smell]:
        """The `broad_test_asserts` findings of a new file `rel` holding `text`, in a fresh repo."""
        r = self.repo({"README.md": "x\n"})
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(text)
        found, _ = find_smells(r, [r / rel], "HEAD")
        return [s for s in found if s.metric == METRIC]

    def test_a_test_with_no_assertion_is_told_at_its_languages_level(self) -> None:
        for lang, (tool, rel, empty, _, level) in SAMPLES.items():
            with self.subTest(lang):
                if not shutil.which(tool):
                    self.skipTest(f"{tool} missing")
                found = self.found(rel, empty)
                self.assertEqual([(s.level, s.key) for s in found], [(level, ASSERTS_NOTHING)])
                self.assertIn("test(s) that assert nothing", found[0].text())

    def test_a_test_that_asserts_is_left_alone(self) -> None:
        for lang, (tool, rel, _, asserting, _) in SAMPLES.items():
            with self.subTest(lang):
                if not shutil.which(tool):
                    self.skipTest(f"{tool} missing")
                self.assertEqual(self.found(rel, asserting), [])

    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_a_go_test_that_hands_t_to_a_helper_may_assert(self) -> None:
        helper = rows(*GO_HEAD, "func TestA(t *testing.T) {", "\tcheck(t, f())", "}")
        self.assertEqual(self.found("a_test.go", helper), [])
        unnamed = rows(*GO_HEAD, "func TestA(_ *testing.T) {", "\tcheck(nil, f())", "}")
        self.assertEqual([s.level for s in self.found("a_test.go", unnamed)], ["hint"])

    @unittest.skipUnless(shutil.which("oxlint"), "oxlint missing")
    def test_a_vitest_assert_counts_as_an_assertion(self) -> None:
        vitest = rows('import { assert, test } from "vitest";', 'test("t", () => {', "  assert.equal(f(), 1);", "});")
        self.assertEqual(self.found("src/a.test.ts", vitest), [])

    def test_python_reads_unittest_pytest_and_raise_as_assertions(self) -> None:
        text = rows("import pytest", "import unittest", "", "", "class T(unittest.TestCase):", "    def test_a(self):",
                    "        self.assertEqual(f(), 1)", "", "    def test_b(self):", "        self.fail('no')", "", "",
                    "def test_c():", "    with pytest.raises(ValueError, match='x'):", "        f()", "", "",
                    "def test_d():", "    raise AssertionError", "", "", "def test_e(mock):",
                    "    mock.assert_called_once()")
        self.assertEqual(self.found("tests/test_a.py", text), [])

    def test_a_broad_assertion_and_an_empty_test_read_apart(self) -> None:
        if not shutil.which("ruff"):
            self.skipTest("ruff missing")
        text = rows("import pytest", "", "", "def test_a():", "    with pytest.raises(ValueError):", "        f()", "",
                    "", "def test_b():", "    f()")
        found = sorted(self.found("tests/test_a.py", text), key=lambda s: s.line)
        self.assertEqual([(s.level, s.added) for s in found], [("hint", [5]), (NIT, [9])])
        self.assertIn("too broad test assertion(s)", found[0].text())
        self.assertIn("test(s) that assert nothing", found[1].text())

    def test_a_code_file_has_no_test_to_judge(self) -> None:
        self.assertEqual(self.found("lib/a.py", rows("def test_a():", "    x = 1")), [])


if __name__ == "__main__":
    unittest.main()
