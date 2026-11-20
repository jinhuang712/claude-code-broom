"""What broom reads from Rust source itself: the cases the language matrix's one sample per smell leaves out, what
and what stays quiet. Sample code is a list of lines, so that none of it stands in this
file as code of its own."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from typing import List, Tuple

from support import BroomCase

from broom.rustmeasure import clean, dropped_unwinds, magic_lines, test_start, type_sizes
from broom.smells import find_smells
from broom.testrot import rust_untested


def rows(*lines: str) -> List[str]:
    """The cleaned rows of a file made of `lines`."""
    return clean("\n".join(lines) + "\n")[0]


class TextTest(unittest.TestCase):
    def test_strings_and_comments_hide_their_numbers_and_braces(self) -> None:
        cleaned, comments = clean('let s = "x * 86400 // no";\n// let y = 3;\nlet c = \'{\';\n')
        self.assertNotIn("86400", "".join(cleaned))
        self.assertNotIn("{", cleaned[2])
        self.assertEqual(comments, [(2, "// let y = 3;")])

    def test_magic_numbers_are_those_compared_computed_returned_or_passed(self) -> None:
        found = rows("const LIMIT: u64 = 86400;", "#[repr(align(64))]", "pub enum E { A = 7 }", "fn f(x: u64) {",
                     "    let v = [0u8; 64];", "    let n = 2 * x + 1;", "    if x > 3600 {}", "    g(42);",
                     "    for i in 0..10 {}", "    x.0", "    let d = shuffle::<3, 4>(a);", "    let t = [3, 4];", "}")
        self.assertEqual(list(magic_lines(found, len(found))), [7, 8, 9])

    def test_test_code_starts_at_cfg_test_or_under_tests(self) -> None:
        self.assertEqual(test_start("src/a.rs", rows("fn f() {}", "#[cfg(test)]", "mod tests {}")), 1)
        self.assertEqual(test_start("tests/it.rs", rows("fn f() {}")), 0)

    def test_a_type_counts_its_impls_whatever_their_generics(self) -> None:
        sizes = type_sizes(rows("pub struct Big<T> {", "    x: T,", "}", "impl<'a, F: Fn() -> u8> Display for Big<F> {",
                                "    fn f() {}", "}", "pub struct Unit;"))
        self.assertEqual(sizes, {"Big": [1, 6], "Unit": [7, 1]})

    def test_a_dropped_catch_unwind_is_a_statement_or_assigned_to_the_blank(self) -> None:
        found = rows("fn f() {", "    let _ = catch_unwind(|| g());", "    panic::catch_unwind(|| {", "        g()",
                     "    });", "    let kept = catch_unwind(|| g());", "    std::panic::catch_unwind(|| g())", "}")
        self.assertEqual(list(dropped_unwinds(found)), [2, 3])


class RustRepoCase(BroomCase):
    def changed(self, base: dict, change: dict) -> Tuple[Path, List[Tuple[str, str]]]:
        """The repo and the (smell, file) pairs a change makes in a crate of the files `base`."""
        r = self.repo({"Cargo.toml": '[package]\nname = "x"\nversion = "0.1.0"\n', **base})
        for rel, body in change.items():
            (r / rel).parent.mkdir(parents=True, exist_ok=True)
            (r / rel).write_text(body)
        found, _ = find_smells(r, [r / rel for rel in change], "HEAD")
        return r, [(s.metric, s.file.relative_to(r).as_posix()) for s in found]


class QuietTest(RustRepoCase):
    def test_a_plain_static_a_doc_comment_and_a_named_should_panic_are_quiet(self) -> None:
        change = {"tests/it.rs": "\n".join(["static NAMES: &[&str] = &[];", "/// let x = 1;", "#[test]",
                                            '#[should_panic(expected = "boom")]', "fn t() {}", ""])}
        _, found = self.changed({}, change)
        self.assertEqual([f for f in found if f[0] in ("globals", "commented_code", "broad_test_asserts")], [])

    def test_a_file_with_its_tests_inside_or_beside_it_is_tested(self) -> None:
        self.assertFalse(rust_untested("src/a.rs", "#[cfg(test)]\nmod tests {}\n", set()))
        self.assertFalse(rust_untested("src/a.rs", "", {"src/a/tests.rs"}))
        self.assertFalse(rust_untested("src/a.rs", "", {"tests/a.rs"}))
        self.assertFalse(rust_untested("src/main.rs", "", set()))
        self.assertTrue(rust_untested("src/a.rs", "", {"tests/b.rs"}))


@unittest.skipUnless(shutil.which("cargo-clippy"), "cargo clippy missing")
class ClippyTest(RustRepoCase):
    def test_an_error_mapped_unread_is_a_broad_catch(self) -> None:
        change = {"src/lib.rs": "\n".join(["//! A crate.", "/// P.", "pub fn p(s: &str) -> Result<i32, String> {",
                                           '    s.parse::<i32>().map_err(|_| String::from("bad"))', "}", ""])}
        _, found = self.changed({"src/lib.rs": "//! A crate.\n"}, change)
        self.assertIn(("broad_catch", "src/lib.rs"), found)


if __name__ == "__main__":
    unittest.main()
