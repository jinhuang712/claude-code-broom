"""How clippy's and rustc's messages read as smells, with no cargo: canned rows of cargo's JSON output over a file on
disk, the place of a parameter, and the config clippy runs with."""

from __future__ import annotations

import json
import shutil
import unittest
from typing import Tuple

from support import BroomCase

from broom.config import SMELL_LIMITS
from broom.realtree import rust_messages
from broom.rustlint import RUST_FLAGS, RUST_LINTS, RUSTC_ASKED, config_text, fn_name, in_parameters, thresholds
from broom.rustmeasure import rust_tree

SOFT = {metric: pair[0] for metric, pair in SMELL_LIMITS.items()}


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

    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_the_place_of_a_parameter_is_told_from_the_body_and_from_a_closure(self) -> None:
        (self.tmp / "a.rs").write_text("pub fn apply<F: Fn(i32) -> i32>(f: F, (x, _): (i32, u8)) -> i32 {\n"
                                       "    let y = |x: i32| f(x);\n    y(1)\n}\n"
                                       "    pub(crate) async fn run<T>(t: T) {}\n")
        tree = rust_tree(self.tmp, ["a.rs"], [])["a.rs"]
        self.assertTrue(in_parameters(tree, 1, "x"))
        self.assertFalse(in_parameters(tree, 2, "x"))
        self.assertFalse(in_parameters([], 1, "x"))
        self.assertEqual((fn_name(tree, 5), fn_name(tree, 2)), ("run", "function"))

    def test_the_config_holds_the_soft_limits_and_each_lint_is_asked_for_once(self) -> None:
        text = config_text({**SOFT, "function_lines": 30, "complexity": 7, "nesting": 3})
        for line in ("too-many-lines-threshold = 30", "cognitive-complexity-threshold = 7",
                     "excessive-nesting-threshold = 4", "too-many-arguments-threshold = 5"):
            self.assertIn(line, text)
        asked = [c for c in RUST_LINTS if c.startswith("clippy::") or c in RUSTC_ASKED]
        self.assertEqual(len(RUST_FLAGS), 2 * len(asked))
        self.assertIn("missing_docs", RUST_FLAGS)
        self.assertNotIn("-W dead_code", " ".join(RUST_FLAGS))
