"""The code smells Rust gets from clippy and rustc: sizes, dead code, TODOs, dropped errors and unused parameters, each
on the lines a change added, with tests left out."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Tuple

from support import BroomCase

from broom.config import SMELL_LIMITS
from broom.realtree import rust_messages
from broom.rustlint import FN_NAME, RUST_FLAGS, RUST_LINTS, config_text, in_parameters, thresholds
from broom.smells import find_smells

HAS_CLIPPY = bool(shutil.which("cargo") and shutil.which("cargo-clippy"))
SOFT = {metric: pair[0] for metric, pair in SMELL_LIMITS.items()}
CARGO = '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'
# Small limits keep the samples short: a function is long past 11 lines and blocked past 14, and so on.
CONFIG = json.dumps({"limits": {"function_lines": [11, 14], "complexity": [4, 8], "nesting": [2, 3]}})
CLEAN = "pub fn double(x: i32) -> i32 {\n    x * 2\n}\n"


def long_fn(name: str, lines: int, step: int) -> str:
    """A function whose body is `lines` lines of code; another `step` makes another body, so two aren't a clone."""
    return (f"pub fn {name}(mut x: i32) -> i32 {{\n"
            + "".join(f"    x += {i * step};\n" for i in range(lines - 1)) + "    x\n}\n")


def branchy_fn(name: str, branches: int) -> str:
    """A function with `branches` sequential ifs: cognitive complexity grows by one with each."""
    return (f"pub fn {name}(mut x: i32) -> i32 {{\n"
            + "".join(f"    if x == {i} {{ x += {i * 3 + 1}; }}\n" for i in range(branches)) + "    x\n}\n")


DEEP = """pub fn deep(x: i32) -> i32 {
    if x > 0 {
        if x > 1 {
            if x > 2 {
                return x;
            }
        }
    }
    0
}
"""
PRESENCE = """pub fn later() {
    todo!()
}

pub fn never() {
    unimplemented!("nope")
}

fn never_called() {}

pub fn drops() {
    let _ = std::fs::remove_file("x");
}

pub fn ignores(used: i32, spare: i32) -> i32 {
    let local = 3;
    used
}
"""
SMELLY = "\n".join([long_fn("long_soft", 12, 1), long_fn("long_hard", 16, 7), branchy_fn("branchy_soft", 5),
                    branchy_fn("branchy_hard", 9), DEEP, PRESENCE])
TESTS = """
#[cfg(test)]
mod tests {
    #[test]
    fn a_long_test_may_unwrap_print_and_leave_things_undone() {
        let value = "1".parse::<i32>().unwrap();
        println!("value {}", value);
        let _ = std::fs::remove_file("x");
        let unused = 3;
        if value > 0 {
            if value > 1 {
                if value > 2 {
                    todo!();
                }
            }
        }
        let mut x = value;
        x += 1;
        x += 2;
        x += 3;
        x += 4;
        x += 5;
        x += 6;
        x += 7;
        x += 8;
        x += 9;
    }

    fn helper_nothing_calls() {}
}
"""
INTEGRATION = """#[test]
fn an_integration_test_may_do_the_same() {
    let n = "2".parse::<i32>().unwrap();
    print!("{}", n);
    let _ = std::fs::read("y");
    let spare = 4;
    if n > 0 { if n > 1 { if n > 2 { todo!(); } } }
    let mut total = n;
    total *= 11;
    total *= 12;
    total *= 13;
    total *= 14;
    total *= 15;
    total *= 16;
    total *= 17;
    total *= 18;
    total *= 19;
}
"""


def message(code: str, text: str, source: str, *places: Tuple[int, str]) -> str:
    """A row of cargo's JSON output: a diagnostic of src/lib.rs with a primary span at each of `places`, a line and the
    name the span marks on it."""
    lines = source.splitlines()
    spans = []
    for line, name in places:
        col = lines[line - 1].index(name) + 1 if name else 1
        row = {"text": lines[line - 1], "highlight_start": col, "highlight_end": col + len(name)}
        spans.append({"file_name": "src/lib.rs", "line_start": line, "column_start": col, "is_primary": True,
                      "text": [row]})
    return json.dumps({"reason": "compiler-message", "message": {"code": {"code": code}, "message": text,
                                                                 "spans": spans}})


class RustMessageTest(BroomCase):
    """How messages read, with no cargo: canned rows of its JSON output over a file on disk."""

    def found(self, source: str, *rows: str) -> list:
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src/lib.rs").write_text(source)
        found = rust_messages(self.tmp, self.tmp, "\n".join(rows), SOFT)
        return [(f.metric, f.line, f.key, f.value) for f in found]

    def test_a_size_comes_from_the_message_and_the_name_from_the_line_of_the_function(self) -> None:
        source = "pub fn big(a: i32) -> i32 {\n    a\n}\n"
        rows = [message("clippy::too_many_lines", "this function has too many lines (61/50)", source, (1, "big")),
                message("clippy::cognitive_complexity", "the function has a cognitive complexity of (14/10)", source,
                        (1, "big")),
                message("clippy::too_many_arguments", "this function has too many arguments (9/7)", source,
                        (1, "big"))]
        self.assertEqual(self.found(source, *rows), [("function_lines", 1, "big", 61), ("complexity", 1, "big", 14),
                                                     ("params", 1, "big", 9)])

    def test_a_nested_block_counts_one_level_past_the_soft_limit_since_the_message_names_no_depth(self) -> None:
        source = "pub fn f(x: i32) {\n    if x > 0 {\n    }\n}\n"
        found = self.found(source, message("clippy::excessive_nesting", "this block is too nested", source, (2, "{")))
        self.assertEqual(found, [("nesting", 2, "function", SOFT["nesting"] + 1)])
        self.assertEqual(thresholds(SOFT)["nesting"], SOFT["nesting"] + 1)

    def test_dead_code_is_named_by_what_the_message_marks_one_message_can_name_two_and_a_twin_adds_nothing(self) -> None:
        source = "fn first() {}\nfn second() {}\nfn third() {}\n"
        names = message("dead_code", "functions `first` and `second` are never used", source, (1, "first"),
                        (2, "second"))
        third = message("dead_code", "function `third` is never used", source, (3, "third"))
        self.assertEqual(self.found(source, names, third, third),  # the crate was built twice, so third was said twice
                         [("dead_code", 1, "first", 1), ("dead_code", 2, "second", 1), ("dead_code", 3, "third", 1)])

    def test_an_unused_variable_counts_only_where_it_is_a_parameter(self) -> None:
        source = ("pub fn f(\n    used: i32,\n    spare: i32,\n) -> i32 {\n    let local = 1;\n"
                  "    let g = |unused: i32| used;\n    g(1)\n}\n")
        rows = [message("unused_variables", f"unused variable: `{name}`", source, (line, name))
                for line, name in ((3, "spare"), (5, "local"), (6, "unused"))]
        self.assertEqual(self.found(source, *rows), [("unused_params", 3, "function", 1)])

    def test_the_place_of_a_parameter_is_told_from_the_body_and_from_a_closure(self) -> None:
        source = "pub fn apply<F: Fn(i32) -> i32>(f: F, x: i32) -> i32 {\n    let y = f(x);\n    y\n}\n"
        self.assertTrue(in_parameters(source, 1, source.index("x: i32") + 1))
        self.assertFalse(in_parameters(source, 2, 9))
        self.assertFalse(in_parameters("", 1, 1))
        self.assertEqual(FN_NAME.search("    pub(crate) async fn run<T>(x: T) {")[1], "run")

    def test_the_config_holds_the_soft_limits_and_each_lint_is_asked_for_once(self) -> None:
        text = config_text({**SOFT, "function_lines": 30, "complexity": 7, "nesting": 3})
        for line in ("too-many-lines-threshold = 30", "cognitive-complexity-threshold = 7",
                     "excessive-nesting-threshold = 4", "too-many-arguments-threshold = 5"):
            self.assertIn(line, text)
        self.assertEqual(len(RUST_FLAGS), 2 * len([c for c in RUST_LINTS if c.startswith("clippy::")]))
        self.assertNotIn("-W dead_code", " ".join(RUST_FLAGS))


@unittest.skipUnless(HAS_CLIPPY, "cargo clippy missing")
class RustSmellTest(BroomCase):
    def crate(self, text: str) -> Path:
        return self.repo({"Cargo.toml": CARGO, "src/lib.rs": text, ".broom.json": CONFIG})

    def smells(self, r: Path) -> list:
        found, _ = find_smells(r, [r / "src/lib.rs"], "HEAD")
        return found

    def test_each_smell_is_found_on_a_line_the_change_adds_at_its_level(self) -> None:
        r = self.crate(CLEAN)
        (r / "src/lib.rs").write_text(CLEAN + "\n" + SMELLY)
        found = self.smells(r)
        self.assertEqual(sorted((s.level, s.metric, s.key) for s in found if s.metric not in {"todo", "unused_params"}),
                         [("block", "complexity", "branchy_hard"), ("block", "function_lines", "long_hard"),
                          ("hint", "complexity", "branchy_soft"), ("hint", "dead_code", "never_called"),
                          ("hint", "function_lines", "long_soft"), ("hint", "nesting", "function"),
                          ("hint", "swallowed_error", "swallowed_error")])
        lines = (CLEAN + "\n" + SMELLY).splitlines()
        by = {s.metric: s for s in found if s.metric in {"todo", "unused_params"}}
        self.assertEqual([lines[n - 1].strip() for n in by["todo"].added], ["todo!()", 'unimplemented!("nope")'])
        self.assertEqual([lines[n - 1].strip() for n in by["unused_params"].added],
                         ["pub fn ignores(used: i32, spare: i32) -> i32 {"], "the unused local is not one")
        self.assertTrue(all(s.level == "hint" for s in by.values()))

    def test_what_the_change_did_not_add_stays_quiet_and_a_long_function_it_edits_is_told_as_touched(self) -> None:
        text = CLEAN + "\n" + SMELLY
        r = self.crate(text)
        (r / "src/lib.rs").write_text(text + "\n// a note\n")
        self.assertEqual(self.smells(r), [])
        (r / "src/lib.rs").write_text(text.replace("x += 3;", "x += 33;", 1))  # inside long_soft, which comes first
        found = self.smells(r)
        self.assertEqual([(s.level, s.metric, s.key, s.touched) for s in found],
                         [("hint", "function_lines", "long_soft", True)], "long_hard, beside it, isn't touched")
        self.assertIn("you touched it, clean it up in this change", found[0].text())

    def test_tests_are_left_out_of_every_new_lint_and_the_rest_of_the_file_still_counts(self) -> None:
        r = self.crate(CLEAN)
        (r / "src/lib.rs").write_text(CLEAN + TESTS)
        (r / "tests").mkdir()
        (r / "tests/it.rs").write_text(INTEGRATION)
        found, _ = find_smells(r, [r / "src/lib.rs", r / "tests/it.rs"], "HEAD")
        self.assertEqual([(s.metric, s.line) for s in found], [], "a long test, its unwraps, todo!() and dead helper")
        (r / "src/lib.rs").write_text(PRESENCE + TESTS)
        found = {s.metric: s for s in self.smells(r)}
        self.assertEqual(len(found["todo"].added), 2, "clippy ran: the two in the code, not the one in the test")


if __name__ == "__main__":
    unittest.main()
