"""The language matrix for Rust: one sample per smell it can have, all of them: its ternary is a nested `if` expression.
Most samples change the crate root, so clippy builds them. See language_matrix."""

from __future__ import annotations

import language_matrix as matrix
from language_matrix import RUST_EXEMPT, Sample, repeated, text

# Pieces, so that this file holds no suppression, TODO or skip of its own.
ALLOW = "#[al" + "low(dead_code)]"
TODO = "to" + "do!()"
IGNORE = "#[ig" + "nore]"
CARGO = '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'
ROOT = "//! A crate.\n"
SCAFFOLD = {"Cargo.toml": CARGO, "src/lib.rs": ROOT}
CLIPPY = ("cargo-clippy",)
CLONE = repeated("    total += values[{i}] + offsets[{i}] * scale;", 40)
TESTS = text(ROOT, "#[cfg(test)]", "mod tests {", "    #[test]", "    fn old() {}", "}")


def lib(*rows: str) -> dict:
    """A change of the crate root to the doc line and `rows`."""
    return {"src/lib.rs": text(ROOT.strip(), "", *rows)}


def method(name: str, lines: int) -> str:
    """A method of Big that is `lines` lines long, in an impl block of its own."""
    return text("impl Big {", f"    /// {name}.", f"    pub fn {name}(&mut self) {{",
                *["        self.x += 1;"] * (lines - 2), "    }", "}", "")


def summed(name: str) -> str:
    """A function that sums 40 lines of the same shape: two of them are a clone."""
    return (f"/// Sums.\npub fn {name}(values: &[i32], offsets: &[i32], scale: i32) -> i32 {{\n    let mut total = 0;\n"
            + CLONE + "    total\n}\n")


CYCLE = {"src/lib.rs": text(ROOT.strip(), "pub mod a;", "pub mod b;"), "src/a.rs": "pub struct A;\n",
         "src/b.rs": text("use crate::a::A;", "", "pub fn f(_: A) {}")}
LAYERS = {"src/lib.rs": text(ROOT.strip(), "pub mod auth;", "pub mod ui;"), "src/auth/mod.rs": "pub mod login;\n",
          "src/auth/login.rs": "pub const VALUE: i32 = 1;\n",
          "src/ui/mod.rs": text("use crate::auth::login::VALUE;", "", "pub const SHOWN: i32 = VALUE;")}

SAMPLES = {
    "function_lines": Sample(lib("/// Long.", "pub fn long_one(mut x: i32) -> i32 {",
                                 *(f"    x += {i};" for i in range(58)), "    x", "}"), CLIPPY),
    "file_lines": Sample(lib(*(f'pub const V{i}: &str = "a";' for i in range(450)))),
    "params": Sample(lib("/// Many.", "pub fn many(a: i32, b: i32, c: i32, d: i32, e: i32, f: i32, g: i32) -> i32 {",
                         "    a + b + c + d + e + f + g", "}"), CLIPPY),
    "nesting": Sample(lib("/// Deep.", "pub fn deep(a: bool) -> i32 {", "    if a {", "        if a {",
                          "            if a {", "                if a {", "                    if a {",
                          "                        if a {", "                            return 1;",
                          "                        }", "                    }", "                }", "            }",
                          "        }", "    }", "    0", "}"), CLIPPY),
    "complexity": Sample(lib("/// Branchy.", "pub fn branchy(mut x: i32) -> i32 {",
                             *(f"    if x == {i} {{\n        x += {i + 1};\n    }}" for i in range(12)), "    x", "}"),
                         CLIPPY),
    "type_lines": Sample({"src/big.rs": text("pub struct Big {", "    x: i32,", "}", "") + method("a", 100)
                          + method("b", 100) + method("c", 60)}),
    "duplicate_lines": Sample({"src/b.rs": summed("two")}, ("jscpd",), base={"src/a.rs": summed("one")}),
    "dead_code": Sample(lib("fn helper() -> i32 {", "    3", "}"), CLIPPY),
    "suppression": Sample(lib(ALLOW, "fn helper() {}"), CLIPPY),
    "swallowed_error": Sample(lib("/// Drops.", "pub fn drops() {", '    let _ = std::fs::remove_file("x");', "}"),
                              CLIPPY),
    "commented_code": Sample(lib("/// F.", "pub fn f() -> i32 {", "    // let y = compute(1, 2);", "    1", "}")),
    "unused_params": Sample(lib("/// F.", "pub fn f(a: i32, unused: i32) -> i32 {", "    a", "}"), CLIPPY),
    "nested_ternary": Sample(lib("/// F.", "pub fn f(a: bool, b: bool) -> i32 {",
                                 "    let x = if a { if b { 1 } else { 2 } } else { 3 };", "    x", "}")),
    "magic_numbers": Sample(lib("/// F.", "pub fn f(x: u64) -> u64 {", "    x * 86400", "}")),
    "debug_output": Sample(lib("/// F.", "pub fn f(x: i32) {", '    println!("x is {}", x);', "}"), CLIPPY),
    "todo": Sample(lib("/// Later.", "pub fn later() {", f"    {TODO}", "}"), CLIPPY),
    "type_escape": Sample(lib("/// F.", "pub fn f(s: &str) -> i32 {", "    s.parse().unwrap()", "}"), CLIPPY),
    "globals": Sample(lib("static mut COUNTER: u32 = 0;")),
    "bool_params": Sample(lib("/// F.", "pub fn f(a: i32, verbose: bool) -> i32 {", "    if verbose { a } else { 0 }",
                              "}"), CLIPPY),
    "broad_test_asserts": Sample({"tests/it.rs": text("#[test]", "#[should_panic]", "fn panics() {",
                                                      '    panic!("any");', "}")}),
    "broad_catch": Sample(lib("/// F.", "pub fn f(s: &str) -> i32 {", "    match s.parse::<i32>() {",
                              "        Ok(n) => n,", "        Err(_) => 0,", "    }", "}")),
    "missing_docs": Sample(lib("pub fn fresh() -> i32 {", "    3", "}"), CLIPPY),
    "import_cycle": Sample({"src/a.rs": text("use crate::b::f;", "", "pub struct A;", "", "pub fn g() {", "    f(A);",
                                             "}")}, base=CYCLE),
    "folder_cycle": Sample({"src/auth/login.rs": text("use crate::ui::SHOWN;", "", "pub const VALUE: i32 = 1;",
                                                      "pub const SEEN: i32 = SHOWN;")}, base=LAYERS),
    "skipped_test": Sample({"src/lib.rs": TESTS.replace("    fn old() {}", f"    fn old() {{}}\n    #[test]\n"
                                                                          f"    {IGNORE}\n    fn later() {{}}")},
                           base={"src/lib.rs": TESTS}),
    "untested_file": Sample({"src/fresh.rs": repeated("pub const C{i}: i32 = {i};", 30)}),
    "deprecated_api": Sample(lib("/// F.", "pub fn f(s: &str) -> &str {", "    s.trim_left()", "}"), CLIPPY),
}


class RustMatrix(matrix.MatrixCase):
    EXEMPT = RUST_EXEMPT
    SCAFFOLD = SCAFFOLD
    SAMPLES = SAMPLES
