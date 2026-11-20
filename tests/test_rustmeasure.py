"""What broom reads from Rust source itself, from its syntax tree: the cases the language matrix's one sample per smell
leaves out, what is found and what stays quiet, among them what a text pattern got wrong. Sample code is a list of
lines, so that none of it stands in this file as code of its own."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from typing import List, Tuple

from support import BroomCase

from broom.config import SMELL_LIMITS
from broom.reading import Reader
from broom.rustmeasure import files_with_tests, rust_text
from broom.smells import find_smells
from broom.testrot import rust_untested

HAS_SG = shutil.which("ast-grep") is not None


@unittest.skipUnless(HAS_SG, "ast-grep missing")
class TreeTest(BroomCase):
    def found(self, *lines: str, rel: str = "src/a.rs") -> List[Tuple[int, str]]:
        """The (line, smell) rows broom reads from a Rust file made of `lines`."""
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
        r = Reader(self.tmp, "broom", [])
        rust_text(r, [rel], SMELL_LIMITS)
        return sorted((row.line, row.metric) for row in r.rows)

    def lines(self, smell: str, *lines: str, rel: str = "src/a.rs") -> List[int]:
        """The lines of `smell` broom reads from a Rust file made of `lines`."""
        return [line for line, metric in self.found(*lines, rel=rel) if metric == smell]

    def test_magic_numbers_are_those_compared_computed_returned_or_passed(self) -> None:
        self.assertEqual(self.lines("magic_numbers", "const LIMIT: u64 = 86400;", "#[repr(align(64))]",
                                    "pub enum E { A = 7 }", "fn f(x: u64) {", "    let v = [0u8; 64];",
                                    "    let n = 2 * x + 1;", "    if x > 3600 {}", "    g(42);",
                                    "    for i in 0..10 {}", "    let d = shuffle::<3, 4>(a);", "    let t = [3, 4];",
                                    "    x.0", "}"), [7, 8, 9])

    def test_a_number_in_a_string_or_raw_string_or_test_code_is_no_magic(self) -> None:
        self.assertEqual(self.lines("magic_numbers", "fn f() {", '    let s = "x * 86400";',
                                    '    let r = r#"y == "77" * 3"#;', "}", "#[cfg(test)]", "mod tests {",
                                    "    fn t() { g(42); }", "}"), [])

    def test_a_type_counts_its_impls_whatever_their_generics(self) -> None:
        method = ["impl<'a, F: Fn() -> u8> Display for Big<F> {", *["    fn f() {}"] * 260, "}"]
        self.assertEqual(self.found("pub struct Big<T> {", "    x: T,", "}", *method, "pub struct Unit;"),
                         [(1, "type_lines")])

    def test_a_dropped_catch_unwind_is_a_statement_or_assigned_to_the_blank(self) -> None:
        self.assertEqual(self.lines("broad_catch", "fn f() {", "    let _ = catch_unwind(|| g());",
                                    "    panic::catch_unwind(|| {", "        g()", "    });",
                                    "    let kept = catch_unwind(|| g());", "    match r {", "        Ok(n) => n,",
                                    "        Err(_) => 0,", "    };", "    std::panic::catch_unwind(|| g())", "}"),
                         [2, 3, 9])

    def test_global_state_is_a_static_item_and_not_its_text_in_a_string(self) -> None:
        self.assertEqual(self.lines("globals", "static mut COUNTER: u32 = 0;", "static NAMES: &[&str] = &[];",
                                    "static LOCK: Mutex<u8> = Mutex::new(0);", 'const S: &str = "static mut X: u8 = 0;";',
                                    'const R: &str = r#"static mut Y: u8 = "0";"#;'), [1, 3])

    def test_commented_code_is_a_comment_that_parses_as_code(self) -> None:
        self.assertEqual(self.lines("commented_code", "fn f() -> i32 {", "    // let y = compute(1, 2);",
                                    "    // This is fine;", "    /// let x = 1;", "    // if ready {",
                                    "    //     go();", "    // }", "    // Safety: the pointer is valid.",
                                    "    // see foo(bar) for more", "    1", "}"), [2, 5])

    def test_any_error_passes_only_in_test_code(self) -> None:
        body = ["#[test]", "#[should_panic]", "fn t() {", "    assert!(f().is_err());",
                '    assert!(f().is_err(), "msg");', "    assert!(matches!(g(), Err(_)));",
                "    assert!(matches!(g(), Err(E::Bad)));", "}", "#[test]", '#[should_panic(expected = "boom")]',
                "fn u() {}"]
        self.assertEqual(self.lines("broad_test_asserts", *body, rel="tests/it.rs"), [2, 4, 5, 6])
        self.assertEqual(self.lines("broad_test_asserts", "fn f() {", "    assert!(f().is_err());", "}"), [])

    def test_a_nested_if_counts_where_it_gives_a_value_and_an_else_if_chain_stays_flat(self) -> None:
        self.assertEqual(self.lines("nested_ternary", "fn f() -> i32 {",
                                    "    let x = if a { if b { 1 } else { 2 } } else { 3 };",
                                    "    let y = if a { 1 } else if b { 2 } else { 3 };",
                                    "    let z = if a { 1 } else { 2 };",
                                    "    if a { if b { g() } else { h() } } else { k() }",
                                    "    g(if a { 1 } else { if b { 2 } else { 3 } });",
                                    "    if a { if b { g(); } }",
                                    "    if a { if b { 1 } else { 2 } } else { 3 }", "}"), [2, 6, 8])

    def test_a_region_the_grammar_cannot_read_is_left_out_with_a_note(self) -> None:
        (self.tmp / "a.rs").write_text("fn f() {\n    @ x * 86400 @\n}\n")
        r = Reader(self.tmp, "broom", [])
        rust_text(r, ["a.rs"], SMELL_LIMITS)
        self.assertEqual([row.metric for row in r.rows if row.line == 2], [])
        self.assertTrue(any("can't parse a.rs" in n for n in r.notes))

    def test_tests_inside_a_file_are_read_from_attributes_not_text(self) -> None:
        (self.tmp / "a.rs").write_text("#[cfg(test)]\nmod tests {}\n")
        (self.tmp / "b.rs").write_text('const S: &str = "#[cfg(test)]";\n// #[test]\n')
        self.assertEqual(files_with_tests(self.tmp, ["a.rs", "b.rs"]), {"a.rs"})


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
        self.assertFalse(rust_untested("src/a.rs", {"src/a.rs"}, set()))
        self.assertFalse(rust_untested("src/a.rs", set(), {"src/a/tests.rs"}))
        self.assertFalse(rust_untested("src/a.rs", set(), {"tests/a.rs"}))
        self.assertFalse(rust_untested("src/main.rs", set(), set()))
        self.assertTrue(rust_untested("src/a.rs", set(), {"tests/b.rs"}))


@unittest.skipUnless(shutil.which("cargo-clippy"), "cargo clippy missing")
class ClippyTest(RustRepoCase):
    def test_an_error_mapped_unread_is_a_broad_catch(self) -> None:
        change = {"src/lib.rs": "\n".join(["//! A crate.", "/// P.", "pub fn p(s: &str) -> Result<i32, String> {",
                                           '    s.parse::<i32>().map_err(|_| String::from("bad"))', "}", ""])}
        _, found = self.changed({"src/lib.rs": "//! A crate.\n"}, change)
        self.assertIn(("broad_catch", "src/lib.rs"), found)


if __name__ == "__main__":
    unittest.main()
