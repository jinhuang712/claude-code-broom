"""A length counts code lines (decision 039): the lines that hold code. A comment line and a blank line never count,
in any language, and a change that adds only those grows nothing and touches nothing. Sample code is a list of lines,
so that a comment in it never stands in this file as one."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from unittest import mock

from support import HAS_SWIFTLINT, BroomCase

from broom.codelines import code_lines, python_code_lines
from broom.config import SMELL_LIMITS
from broom.measure import measure
from broom.smells import find_smells
from broom.swiftkit import library
from broom.syntax import MISSING

HAS_SG = shutil.which("ast-grep") is not None
HAS_OXLINT = shutil.which("oxlint") is not None
LOW = {**SMELL_LIMITS, "function_lines": (5, 100), "type_lines": (5, 1000), "file_lines": (5, 1000)}
QUIET = {"smells_off": ["dead_code", "missing_docs", "untested_file"]}  # not what these tests are about
LENGTHS = ("function_lines", "type_lines", "file_lines")
TOUCHED = "you touched it, clean it up in this change"
NOTES = ("# a note", "", "# another")  # what counts for nothing: comment lines and a blank one


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


def padded(rows: List[str], notes: List[str], every: int = 3) -> List[str]:
    """`rows` with the lines `notes` put in after every `every` of them."""
    out: List[str] = []
    for n, row in enumerate(rows, 1):
        out += [row, *(notes if n % every == 0 else [])]
    return out


def py_function(name: str, lines: int, notes: Tuple[str, ...] = ()) -> str:
    """A Python function of `lines` code lines, with the lines `notes` (indented here) after every third."""
    body = padded([f"    x += {i}" for i in range(lines - 2)], [f"    {n}".rstrip() for n in notes])
    return text(f"def {name}(x):", *body, "    return x")


PY = text('"""Module doc.', "", 'More."""', "import os  # trailing", "", "# a comment", "def f(x):", '    """Doc."""',
          "    y = [", "        1,", "        # inside", "    ]", '    s = """text', "", '    # in a string"""',
          "    return x, y, s")
GO = text("package a", "", "// Doc.", "func f() int {", "\t/* block", "\t   more */", "\tx := 1 // trailing",
          '\ts := "// no comment"', "\t/* a */ y := 2 /* b */", "", "\treturn x + y + len(s)", "}")
TSX = text("const s = `", "// in a template", "`;", "/** Doc. */", "export function f() {", "  // c",
           "  return <b>{/* c */}</b>;", "}")
RUST = text("//! Crate doc.", "", "/// Doc.", "pub fn f() -> i32 {", "    // c", '    let s = "// s";', "    /* b",
            "       b */", "    1", "}")
CSS = text("/* head */", "a {", "  /* c */", "  color: red; /* t */", "", "}")
SCSS = text("// head", "a {", "  // c", "  color: red;", "}")
SWIFT = text("/// Doc.", "func f() -> Int {", "    // c", "    /* b", "       b */", '    let s = "// s"', "",
             "    return s.count // t", "}")


class CodeLinesTest(unittest.TestCase):
    def test_in_python_a_comment_a_docstring_and_a_blank_line_are_no_code_lines(self) -> None:
        self.assertEqual(python_code_lines(PY), {4, 7, 9, 10, 12, 13, 15, 16},
                         "a string that isn't a docstring is code, a blank line inside it is not")
        self.assertEqual(python_code_lines(text("def f(): '''Doc.'''", "x = 1  # why")), {1, 2},
                         "a line that holds code beside a docstring or a comment is a code line")

    def test_past_what_the_tokenizer_reads_every_line_that_isnt_blank_counts(self) -> None:
        broken = text("x = 1", "# c", 's = """open', "# inside", "")
        self.assertEqual(python_code_lines(broken), {1, 3, 4}, "the comment read before the break is still none")

    @unittest.skipUnless(HAS_SG, "ast-grep missing")
    def test_the_languages_ast_grep_reads_take_their_comments_from_the_tree(self) -> None:
        notes: List[str] = []
        found = code_lines({"a.go": GO, "a.tsx": TSX, "a.rs": RUST, "a.css": CSS, "a.scss": SCSS, "a.py": PY}, notes)
        self.assertEqual(notes, [])
        self.assertEqual(found["a.go"], {1, 4, 7, 8, 9, 11, 12}, "code between two comments is code")
        self.assertEqual(found["a.tsx"], {1, 2, 3, 5, 7, 8}, "a template's text is code, a JSX comment beside code too")
        self.assertEqual(found["a.rs"], {4, 6, 9, 10}, "doc comments are comments")
        self.assertEqual((found["a.css"], found["a.scss"]), ({2, 4, 6}, {2, 4, 5}))
        self.assertEqual(found["a.py"], python_code_lines(PY), "Python is read in the same call")

    @unittest.skipUnless(library(), "sourcekitd missing")
    def test_swift_takes_its_comments_from_sourcekit(self) -> None:
        self.assertEqual(code_lines({"a.swift": SWIFT}, [])["a.swift"], {2, 6, 8, 9})

    def test_without_ast_grep_every_line_that_isnt_blank_counts_and_a_note_says_so(self) -> None:
        notes: List[str] = []
        with mock.patch("broom.syntax.shutil.which", return_value=None):
            found = code_lines({"a.go": GO}, notes)
        self.assertEqual((found["a.go"], notes), ({1, 3, 4, 5, 6, 7, 8, 9, 11, 12}, [MISSING]))


class MeasuredLengthTest(unittest.TestCase):
    """What the measurers give for a file in a scratch tree: each length in code lines, with the lines it takes."""

    def lengths(self, files: Dict[str, str]) -> List[Tuple[str, str, str, int, int]]:
        """(file, smell, name, code lines, the lines it takes) of each length past the limits `LOW`."""
        with tempfile.TemporaryDirectory() as tmp:
            rows = measure(Path(tmp) / "now", files, LOW, Path(tmp), [])
        return sorted((r.rel, r.metric, r.key, r.value, r.span) for r in rows if r.metric in LENGTHS)

    def test_a_python_function_a_class_and_a_file_count_their_code_lines(self) -> None:
        klass = text("class Big:", '    """Doc."""', "", *padded([f"    a{i} = {i}" for i in range(6)], ["    # c"]))
        found = self.lengths({"a.py": py_function("long", 8, ("# c", "")) + "\n\n" + klass,
                              "b.py": py_function("short", 5, ("# c", "", "# d"))})
        self.assertEqual(found, [("a.py", "file_lines", "file", 15, 0), ("a.py", "function_lines", "long", 8, 12),
                                 ("a.py", "type_lines", "Big", 7, 10)],
                         "8 code lines in 12, and the function of 5 in 8 lines is under the limit")

    @unittest.skipUnless(HAS_SG, "ast-grep missing")
    def test_a_go_function_and_a_type_with_its_methods_count_their_code_lines(self) -> None:
        body = padded([f"\tx += {i}" for i in range(6)], ["\t// c", "", "\t/* d", "\t   e */"])
        go = text("package a", "", "// Big is big.", "type Big struct {", "\t// its count", "\tn int", "}", "",
                  "// Sum adds.", "func (b *Big) Sum(x int) int {", *body, "\treturn x", "}", "",
                  "func short() int {", "\t// c", "", "\treturn 1", "}")
        found = [row for row in self.lengths({"a.go": go}) if row[1] != "file_lines"]
        self.assertEqual(found, [("a.go", "function_lines", "Sum", 9, 17), ("a.go", "type_lines", "Big", 12, 0)],
                         "the struct's 3 code lines and the method's 9; no linter is asked")

    @unittest.skipUnless(HAS_SG and HAS_OXLINT and shutil.which("node"), "ast-grep, oxlint or node missing")
    def test_a_ts_function_and_a_class_count_their_code_lines(self) -> None:
        body = padded([f"  x += {i};" for i in range(6)], ["  // c", "", "  /* d", "     e */"])
        ts = text("/** Doc. */", "export function long(x: number): number {", *body, "  return x;", "}", "",
                  "export function short(x: number): number {", "  // c", "", "  // d", "", "  return x;", "}", "",
                  "export class Big {", *padded([f"  a{i} = {i};" for i in range(6)], ["  // c", ""]), "}", "",
                  "export class Small {", "  // c", "", "  // d", "", "  // e", "  a = 1;", "}")
        found = [row for row in self.lengths({"a.ts": ts}) if row[1] != "file_lines"]
        self.assertEqual(found, [("a.ts", "function_lines", "long", 9, 17), ("a.ts", "type_lines", "Big", 8, 12)],
                         "the function of 3 code lines and the class of 3 are long only by their comments")

    @unittest.skipUnless(HAS_SG, "ast-grep missing")
    def test_a_rust_type_with_its_impl_and_a_css_file_count_their_code_lines(self) -> None:
        rust = text("/// Big is big.", "pub struct Big {", "    // its count", "    n: i32,", "}", "",
                    "impl Big {", "    /// Adds.", "    pub fn sum(&self) -> i32 {", "        // c", "",
                    "        self.n", "    }", "}")
        css = text("/* head", "   more */", "", *[f".a{i} {{ color: red; }} /* c */" for i in range(6)], "", "/* end */")
        self.assertEqual(self.lengths({"a.rs": rust, "a.css": css}),
                         [("a.css", "file_lines", "file", 6, 0), ("a.rs", "file_lines", "file", 8, 0),
                          ("a.rs", "type_lines", "Big", 8, 0)])

    @unittest.skipUnless(HAS_SWIFTLINT and library(), "swiftlint or sourcekitd missing")
    def test_a_swift_function_and_a_file_count_their_code_lines(self) -> None:
        body = padded([f"    x += {i}" for i in range(6)], ["    // c", "", "    /* d", "       e */"])
        swift = text("/// Doc.", "func long(_ n: Int) -> Int {", "    var x = n", *body, "    return x", "}")
        self.assertEqual(self.lengths({"a.swift": swift}),
                         [("a.swift", "file_lines", "file", 10, 0), ("a.swift", "function_lines", "long", 8, 0)],
                         "SwiftLint counts the body's code lines, and gives no span")


class ChangeTest(BroomCase):
    """A change, as the hooks see it: only code lines grow a length, and only a changed code line touches one."""

    def repo(self, files: dict, config: Optional[dict] = None) -> Path:
        return super().repo({".broom.json": json.dumps({**QUIET, **(config or {})}), **files})

    def smells(self, repo: Path, name: str) -> List[str]:
        """The texts of the length smells found in `name` against HEAD."""
        found, _ = find_smells(repo, [repo / name], "HEAD")
        return [s.text() for s in found if s.metric in LENGTHS]

    def test_a_change_that_adds_only_comments_to_a_file_past_its_hard_limit_passes(self) -> None:
        code = "".join(f"x{i} = {i}\n" for i in range(25))
        r = self.repo({"a.py": code}, {"limits": {"file_lines": [10, 20]}})
        noted = text('"""What the file holds.', "", 'In three lines."""', "", "# Why x0 comes first.") + code + "\n# end\n"
        (r / "a.py").write_text(noted)
        self.assertEqual(self.smells(r, "a.py"), [], "33 lines, and 25 code lines as before")
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.denied(self.commit(r, "git commit -m comments")), "", "so the commit goes through")
        (r / "a.py").write_text(noted + "y = 1\n")
        self.assertEqual(self.smells(r, "a.py"), ["the file is 26 code lines long (hard limit 20; was 25)"])

    def test_comments_added_to_a_long_function_grow_nothing_and_touch_nothing(self) -> None:
        r = self.repo({"a.py": py_function("legacy", 60)})
        (r / "a.py").write_text(py_function("legacy", 60, NOTES))
        self.assertEqual(self.smells(r, "a.py"), [], "60 code lines before and after, and no code line changed")
        (r / "a.py").write_text(py_function("legacy", 60, NOTES).replace("return x", "return x + 0"))
        self.assertEqual(self.smells(r, "a.py"), [f"legacy is 60 code lines long (over 50; was 60: {TOUCHED})"],
                         "its last line lies past its 60th: a function takes the lines of its span")

    def test_a_function_long_only_by_its_comments_is_no_smell(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("noted", 45, NOTES))
        self.assertEqual(self.smells(r, "a.py"), [], "45 code lines in 87")
        (r / "a.py").write_text(py_function("noted", 55, NOTES))
        self.assertEqual(self.smells(r, "a.py"), ["noted is 55 code lines long (over 50; new)"])

    def test_a_new_file_is_untested_by_its_code_lines(self) -> None:
        r = super().repo({"x.py": "x = 1\n"})
        rows = [f"x{i} = {i}" for i in range(12)]
        for name, lines, said in (("notes.py", padded(rows, ["# c", "# d", ""] * 2), 0), ("code.py", rows * 3, 1)):
            with self.subTest(name):
                (r / name).write_text(text(*lines))
                found, _ = find_smells(r, [r / name], "HEAD")
                self.assertEqual(sum(s.metric == "untested_file" for s in found), said)

    def test_stats_counts_the_same_code_lines(self) -> None:
        r = super().repo({"a.py": PY, "b.py": "# only a comment\n\n"})
        done = self.cli(r, "stats", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        size = json.loads(done.stdout)["size"]
        self.assertEqual((size["total"]["lines"], size["longest"][0]), (8, {"file": "a.py", "lines": 8, "test": False}))
        self.assertIn("Size (code lines)", self.cli(r, "stats").stdout)


if __name__ == "__main__":
    unittest.main()
