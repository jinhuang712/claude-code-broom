"""Smells only some languages measure, and what looks like them that must stay quiet."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest import mock

from support import BroomCase

from broom.smells import find_smells


class SmellLanguageTest(BroomCase):
    def test_a_long_rust_or_css_file_is_a_smell_though_no_tool_reads_them(self) -> None:
        r = self.repo({"README.md": "x\n"})
        for rel, line in (("a.rs", "fn f() {}\n"), ("a.css", ".a { color: red; }\n")):
            with self.subTest(rel):
                self.assertIn(("hint", "file_lines"), self.measured(r, rel, "git", line * 450))

    def test_a_copy_of_rust_or_css_code_is_a_smell(self) -> None:
        if not shutil.which("jscpd"):
            self.skipTest("jscpd missing")
        rust = "".join(f"    let value{n} = values[{n}] + offsets[{n}] * scale;\n" for n in range(40))
        css = "".join(f".item{n} {{\n  color: #{n:03d};\n  margin: {n}px;\n}}\n" for n in range(1, 20))
        samples = {"rs": (f"fn one() {{\n{rust}}}\n", f"fn two() {{\n{rust}}}\n"), "css": (css, css)}
        for ext, (old, new) in samples.items():
            with self.subTest(ext):
                r = self.repo({f"a.{ext}": old})
                self.assertIn(("block", "duplicate_lines"), self.measured(r, f"b.{ext}", "git", new))

    def measured(self, r: Path, rel: str, tool: str, text: str) -> list:
        """The smells `text` has as a new file `rel`, or a skipped subtest when the tool is missing."""
        if not shutil.which(tool):
            self.skipTest(f"{tool} missing")
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(text)
        found, _ = find_smells(r, [r / rel], "HEAD")
        return [(s.level, s.metric) for s in found]

    def test_what_only_some_languages_measure(self) -> None:
        samples = {
            "a.py": ("ruff", "def f(x):\n    return 1 if x else (2 if x > 1 else 3)\n", ("block", "nested_ternary")),
            "a.ts": ("oxlint", "export function f(a: number, unused: string): number {\n  return a;\n}\n",
                     ("hint", "unused_params")),
            "go/a.go": ("golangci-lint", "package a\n\nfunc F(a interface{}) string {\n\treturn a.(string)\n}\n",
                        ("hint", "type_escape")),
            "a.swift": ("swiftlint", 'func f() {\n    print("x")\n    NSLog("y")\n}\n', ("hint", "debug_output")),
            "c.ts": ("oxlint", "export function f(a: number, verbose: boolean): number {\n  return verbose ? a : 0;\n}\n",
                     ("hint", "bool_params")),
            "d.ts": ("oxlint", "export class Big {\n" + "".join(f"  m{n}() {{ return this; }}\n" for n in range(260))
                     + "}\n", ("hint", "type_lines")),
            "e.ts": ("oxlint", "// const x = compute(1, 2);\nexport const y = 1;\n", ("note", "commented_code")),
            "f.ts": ("oxlint", "let counter = 0;\nexport function bump(): number {\n  counter += 1;\n  return counter;\n}\n",
                     ("hint", "globals")),
            "g.test.ts": ("oxlint", 'test("t", () => {\n  expect(() => f()).toThrow();\n});\n',
                          ("hint", "broad_test_asserts")),
            "c.swift": ("swiftlint", "func f(a: Int) -> Int {\n    return a > 1 ? (a > 2 ? 1 : 2) : 3\n}\n",
                        ("block", "nested_ternary")),
            "d.swift": ("swiftlint", "var counter = 0\n", ("hint", "globals")),
            "g.swift": ("swiftlint", "func setEnabled(_ enabled: Bool) {}\n", ("hint", "bool_params")),
        }
        r = self.repo({"README.md": "x\n"})
        for rel, (tool, text, expected) in samples.items():
            with self.subTest(rel):
                self.assertIn(expected, self.measured(r, rel, tool, text))

    def test_what_looks_alike_is_not_flagged(self) -> None:
        samples = {
            "b.py": ("ruff", "def f(x):\n    return 1 if x else 2\n", "nested_ternary"),
            "b.ts": ("oxlint", "export function f(a: number, _b: string): number {\n  const unusedVar = a;\n"
                     "  return a;\n}\n", "unused_params"),
            "go/b.go": ("golangci-lint", "package b\n\nfunc F(a interface{}) string {\n\ts, ok := a.(string)\n"
                        '\tif !ok {\n\t\treturn ""\n\t}\n\treturn s\n}\n', "type_escape"),
            "b.swift": ("swiftlint", 'func f(printer: Printer) {\n    printer.print("x")\n}\n', "debug_output"),
            "c.ts": ("oxlint", "export const mapped = [1, 2].map((x: number, ok: boolean) => (ok ? x : 0));\n"
                     "export function g(options: { verbose: boolean }): boolean {\n  return options.verbose;\n}\n",
                     "bool_params"),
            "d.ts": ("oxlint", "// This function computes the total (see docs).\n// Note: foo(bar)\n// TODO: tidy this\n"
                     "/** Documented (with parentheses). */\nexport const y = 1;\n", "commented_code"),
            "e.ts": ("oxlint", "let quiet = 0;\nexport const z = quiet + 1;\n", "globals"),
            "h.test.ts": ("oxlint", 'test("t", () => {\n  expect(() => f()).toThrow("boom");\n});\n',
                          "broad_test_asserts"),
            "e.swift": ("swiftlint", 'func f(a: Int?) -> Int {\n    // x ? y ? 1 : 2 : 3\n    let s = "a ? b ? c : d : e"\n'
                        "    let t = a?.signum() ?? 0\n    return a != nil ? t : s.count\n}\n", "nested_ternary"),
            "f.swift": ("swiftlint", "struct S {\n    var x = 0\n}\n", "globals"),
            "main.swift": ("swiftlint", "var counter = 0\nprint(counter)\n", "globals"),
            "g.swift": ("swiftlint", "func setEnabled(enabled: Bool, _ delay: Int) {}\n", "bool_params"),
        }
        r = self.repo({"README.md": "x\n"})
        for rel, (tool, text, metric) in samples.items():
            with self.subTest(rel):
                self.assertNotIn(metric, [m for _, m in self.measured(r, rel, tool, text)])

    def test_a_ts_file_loses_only_brooms_own_rules_without_node_or_their_plugin(self) -> None:
        if not shutil.which("oxlint"):
            self.skipTest("oxlint missing")
        r = self.repo({"README.md": "x\n"})
        (r / "a.ts").write_text("export function f(a: number, unused: string, flag: boolean): number {\n"
                                "  return a;\n}\n")
        real_which = shutil.which

        def which_without_node(name: str, *args, **kwargs):
            return None if name == "node" else real_which(name, *args, **kwargs)

        cases = (("no node", mock.patch("shutil.which", which_without_node), "node is missing"),
                 ("no plugin", mock.patch("broom.jsmeasure.BROOM_RULES", r / "nope.mjs"), "Failed to load JS plugin"))
        for what, patch, note in cases:
            with self.subTest(what), patch:
                found, notes = find_smells(r, [r / "a.ts"], "HEAD")
                metrics = [s.metric for s in found]
                self.assertIn("unused_params", metrics, "the rest of oxlint still ran")
                self.assertNotIn("bool_params", metrics)
                self.assertTrue(any(note in n for n in notes), notes)
