"""What a syntax tree tells the counters and the skipped-test smell: Python's comments come from its tokens and its
tests and skips from its tree, so a marker or a skip inside a string is none; a skip under a branch is decided by a
condition. Sample code is written as lists of lines, and a skip in two pieces: broom reads its own tests too."""

from __future__ import annotations

import shutil
import unittest

from support import BroomCase

from broom import treefacts

SKIP = "@unittest." + "skip"
XFAIL = "@pytest.mark." + "xfail"
SKIP_TEST = "self." + "skipTest"
TODO = "# TO" + "DO: later"


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


class PythonTest(unittest.TestCase):
    def test_cases_and_skips_with_whether_a_condition_decides_each(self) -> None:
        tree = treefacts.py_tests(text(
            "class T:", f"    {SKIP}('later')", "    def test_a(self):", "        pass",
            f"    {SKIP}If(X, 'x')", "    def test_b(self):", "        if not X:", f"            {SKIP_TEST}('x')",
            f"        {SKIP_TEST}('wip')", "", f"{XFAIL}(sys.platform == 'win32', reason='x')", "def test_c():", "    pass",
            "", f"{XFAIL}", "async def test_d():", "    pass", "", "def helper():", "    pass"))
        self.assertEqual(tree.cases, 4)
        self.assertEqual(tree.skips, [(2, False), (5, True), (8, True), (9, False), (11, True), (15, False)])

    def test_a_skip_inside_a_string_is_none_and_code_that_doesnt_parse_gives_nothing(self) -> None:
        self.assertEqual(treefacts.py_tests(text("s = '''", f"{SKIP}('x')", "def test_a(): pass", "'''")).skips, [])
        self.assertEqual(treefacts.py_tests("def test_a(:\n").cases, 0)

    def test_comments_are_the_comment_tokens_and_a_string_holds_none(self) -> None:
        found = treefacts.py_comments(text(f"x = 1  {TODO}", f"s = '{TODO}'", '"""', TODO, '"""'))
        self.assertEqual(found, {1: TODO})
        self.assertEqual(treefacts.py_comments("x = 1  # plain\n"), {}, "a file with no marker word isn't tokenized")


class AstGrepTest(BroomCase):
    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_go_and_ts_trees_from_one_run_and_a_block_comment_spans_its_lines(self) -> None:
        trees = treefacts.skip_trees({
            "a_test.go": text("package a", "func TestA(t *testing.T) {", '\tt.Skip("x")', "\tif short {",
                              "\t\tt.Skip()", "\t}", "}"),
            "b.test.ts": text("it('a', () => {});", "x" + "it('b', () => {});", "/* TODO:", " FIXME */")}, [])
        self.assertEqual((trees["a_test.go"].cases, trees["a_test.go"].skips), (1, [(3, False), (5, True)]))
        self.assertEqual((trees["b.test.ts"].cases, trees["b.test.ts"].skips), (2, [(2, False)]))
        self.assertEqual(trees["b.test.ts"].comments, {3: "/* TODO:", 4: " FIXME */"})


if __name__ == "__main__":
    unittest.main()
