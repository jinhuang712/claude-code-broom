"""Smells that need the project's real checkout: typed linters, module graphs. Only what the change adds counts."""

from __future__ import annotations

import shutil
import unittest

from support import HAS_GO, BroomCase

from broom.config import SMELL_LIMITS
from broom.realtree import TOOL_TIMEOUT, Budget, clippy_dirs, find_in_real_tree
from broom.smells import find_smells

SOFT = {metric: pair[0] for metric, pair in SMELL_LIMITS.items()}
GO_MOD = "module example.com/x\n\ngo 1.22\n"
GO_CLEAN = 'package main\n\nimport "strings"\n\nfunc Upper(s string) string {\n\treturn strings.ToUpper(s)\n}\n'
GO_SMELLY = """package main

import (
	"fmt"
	"strings"
)

var counter int

func Upper(s string) string {
	fmt.Println("debug")
	// x := compute(1, 2)
	// if x > 3 { return }
	return strings.ToUpper(s)
}

func helper() int {
	return 1
}
"""

CARGO = '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'
RS_CLEAN = "pub fn double(x: i32) -> i32 {\n    x * 2\n}\n"
RS_SMELLY = """pub fn many(a: i32, b: i32, c: i32, d: i32, e: i32, f: i32, g: i32) -> i32 {
    a + b + c + d + e + f + g
}

pub fn flag(x: i32, verbose: bool) -> i32 {
    if verbose {
        println!("x = {}", x);
    }
    x
}

pub fn first(v: Vec<i32>) -> i32 {
    *v.first().unwrap()
}

#[allow(dead_code)]
fn hidden() {}
"""
HAS_CLIPPY = bool(shutil.which("cargo") and shutil.which("cargo-clippy"))


class RealTreeTest(BroomCase):
    def metrics(self, r, rel: str) -> list:
        found, _ = find_smells(r, [r / rel], "HEAD")
        return sorted((s.level, s.metric) for s in found)

    @unittest.skipUnless(HAS_GO, "go or golangci-lint missing")
    def test_go_smells_that_need_types_are_found_on_the_lines_a_change_adds(self) -> None:
        r = self.repo({"go.mod": GO_MOD, "main.go": GO_CLEAN})
        (r / "main.go").write_text(GO_SMELLY)
        self.assertEqual(self.metrics(r, "main.go"),  # `counter` and `helper` are both unused
                         [("hint", "commented_code"), ("hint", "dead_code"), ("hint", "dead_code"),
                          ("hint", "debug_output"), ("hint", "globals")])

    @unittest.skipUnless(HAS_GO, "go or golangci-lint missing")
    def test_a_go_smell_the_change_did_not_add_stays_quiet(self) -> None:
        r = self.repo({"go.mod": GO_MOD, "main.go": GO_SMELLY})
        (r / "main.go").write_text(GO_SMELLY.replace('"debug"', '"debug twice"'))  # the line is edited, not new
        self.assertEqual([m for _, m in self.metrics(r, "main.go")], ["debug_output"], "the edited line only")
        (r / "main.go").write_text(GO_SMELLY + "\n// a note\n")  # a line far from every smell
        self.assertEqual(self.metrics(r, "main.go"), [])

    @unittest.skipUnless(shutil.which("oxlint"), "oxlint missing")
    def test_an_import_that_closes_a_ts_cycle_is_found_where_it_is_added(self) -> None:
        r = self.repo({"a.ts": "export const a = 1;\n", "b.ts": 'import { a } from "./a";\nexport const b = a;\n'})
        (r / "a.ts").write_text('import { b } from "./b";\nexport const a = b;\n')
        self.assertIn(("hint", "import_cycle"), self.metrics(r, "a.ts"))

    @unittest.skipUnless(shutil.which("oxlint"), "oxlint missing")
    def test_a_ts_cycle_that_was_there_before_stays_quiet(self) -> None:
        cycle = {"a.ts": 'import { b } from "./b";\nexport const a = b;\n',
                 "b.ts": 'import { a } from "./a";\nexport const b = a;\n'}
        r = self.repo(cycle)
        (r / "a.ts").write_text(cycle["a.ts"] + "export const other = 2;\n")
        self.assertNotIn("import_cycle", [m for _, m in self.metrics(r, "a.ts")])

    @unittest.skipUnless(HAS_CLIPPY, "cargo clippy missing")
    def test_rust_smells_come_from_clippy_on_the_lines_a_change_adds(self) -> None:
        r = self.repo({"Cargo.toml": CARGO, "src/lib.rs": RS_CLEAN})
        (r / "src/lib.rs").write_text(RS_SMELLY)
        self.assertEqual(self.metrics(r, "src/lib.rs"),
                         [("block", "suppression"), ("hint", "bool_params"), ("hint", "debug_output"),
                          ("hint", "params"), ("hint", "type_escape")])

    @unittest.skipUnless(HAS_CLIPPY, "cargo clippy missing")
    def test_a_rust_smell_the_change_did_not_add_stays_quiet(self) -> None:
        r = self.repo({"Cargo.toml": CARGO, "src/lib.rs": RS_SMELLY})
        (r / "src/lib.rs").write_text(RS_SMELLY + "\n// a note\n")
        self.assertEqual(self.metrics(r, "src/lib.rs"), [])

    def test_a_python_import_that_closes_a_cycle_is_found_where_it_is_added(self) -> None:
        r = self.repo({"pkg/__init__.py": "", "pkg/a.py": "X = 1\n", "pkg/b.py": "from pkg import a\n\nY = a.X\n"})
        (r / "pkg/a.py").write_text("from . import b\n\nX = b.Y\n")
        self.assertIn(("hint", "import_cycle"), self.metrics(r, "pkg/a.py"))

    def test_python_imports_that_break_a_cycle_on_purpose_do_not_close_one(self) -> None:
        r = self.repo({"pkg/__init__.py": "", "pkg/b.py": "from pkg import a\n\nY = a.X\n", "pkg/a.py": "X = 1\n"})
        (r / "pkg/a.py").write_text(
            "from __future__ import annotations\n\nfrom typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n    from . import b\n\n\ndef later() -> int:\n    from . import b\n\n"
            "    return b.Y\n\n\nX = 1\n")
        self.assertNotIn("import_cycle", [m for _, m in self.metrics(r, "pkg/a.py")])

    def test_a_python_cycle_that_was_there_before_stays_quiet(self) -> None:
        cycle = {"pkg/__init__.py": "", "pkg/a.py": "from . import b\n\nX = 1\n", "pkg/b.py": "from . import a\n"}
        r = self.repo(cycle)
        (r / "pkg/a.py").write_text(cycle["pkg/a.py"] + "Z = 2\n")
        self.assertNotIn("import_cycle", [m for _, m in self.metrics(r, "pkg/a.py")])

    def test_clippys_config_and_build_output_stay_where_they_were(self) -> None:
        # cargo checks a crate again when CLIPPY_CONF_DIR changes, so the path must be the same on every run.
        crate = self.tmp / "crate"
        conf, target = clippy_dirs(crate, SOFT)
        self.assertEqual(clippy_dirs(crate, SOFT), (conf, target))
        self.assertIn("too-many-arguments-threshold = 5", (conf / "clippy.toml").read_text())
        for name in ("params", "function_lines", "complexity", "nesting"):
            self.assertNotEqual(clippy_dirs(crate, {**SOFT, name: SOFT[name] + 1})[0], conf,
                                f"another {name} limit, another config, and no rewrite of this one")
        self.assertNotEqual(clippy_dirs(self.tmp / "other", SOFT)[1], target, "each crate has its own build output")

    def test_a_budget_caps_what_the_next_tool_may_take_and_ends_at_zero(self) -> None:
        self.assertEqual(Budget().timeout(), TOOL_TIMEOUT, "no budget leaves each tool its own timeout")
        self.assertEqual(Budget(10_000).timeout(), TOOL_TIMEOUT, "a big one doesn't raise it")
        self.assertLessEqual(Budget(5).timeout(), 5)
        self.assertEqual(Budget(0).timeout(), 0)

    @unittest.skipUnless(HAS_GO and shutil.which("oxlint"), "go, golangci-lint or oxlint missing")
    def test_a_spent_budget_skips_the_tools_and_says_so(self) -> None:
        r = self.repo({"go.mod": GO_MOD, "main.go": GO_SMELLY, "a.ts": "export const a = 1;\n"})
        notes: list = []
        self.assertEqual(find_in_real_tree(r, ["main.go", "a.ts"], SOFT, notes, Budget(0)), [])
        self.assertEqual(sorted(n.split(" before ")[1].split(" measured")[0] for n in notes), ["golangci-lint", "oxlint"])
        self.assertTrue(find_in_real_tree(r, ["main.go"], SOFT, [], Budget(60)), "a roomy budget still measures")
