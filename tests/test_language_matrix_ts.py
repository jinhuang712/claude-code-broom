"""The language matrix for TS/JS: one sample per smell. See language_matrix."""

from __future__ import annotations

import language_matrix as matrix
from language_matrix import Sample, repeated, text

# Pieces, so that this file holds no suppression, TODO or skip of its own.
SUPPRESS = "// @ts-" + "ignore"
TODO = "// TO" + "DO: later"
SKIP = "it." + "skip"
TS_CONFIG = ('{"compilerOptions":{"target":"es2022","module":"nodenext","strict":true,"noEmit":true},'
             '"include":["src"]}\n')
SCAFFOLD = {"package.json": '{"name":"t","private":true,"type":"module"}\n', "tsconfig.json": TS_CONFIG}
CLONE = repeated("  const value{i} = values[{i}] + offsets[{i}] * scale;", 40)
OXLINT = ("oxlint",)
RULES = ("oxlint", "node")  # broom's own rules are oxlint plugins that run on node
HELPER = text("export function helper(): number {", "  return 1;", "}")
CYCLE = {"src/a.ts": "export const a = 1;\n", "src/b.ts": 'import { a } from "./a";\nexport const b = a;\n'}
LAYERS = {"src/auth/login.ts": "export const v = 1;\n", "src/ui/view.ts": 'import { v } from "../auth/login";\n'
                                                                       "export const s = v;\n"}
OLD_API = text("/** Old.", " * @deprecated use newFn instead", " */", "export function oldFn(n: number): number {",
               "  return n;", "}", "", "export function newFn(n: number): number {", "  return n * 2;", "}")

SAMPLES = {
    "function_lines": Sample({"src/a.ts": "export function f(): number {\n  let x = 0;\n" + repeated("  x += {i};", 58)
                              + "  return x;\n}\n"}, OXLINT),
    "file_lines": Sample({"src/a.ts": repeated('export const v{i} = "a";', 450)}),
    "params": Sample({"src/a.ts": text("export function many(a: number, b: number, c: number, d: number, e: number,",
                                       "  f: number, g: number): number {", "  return a + b + c + d + e + f + g;",
                                       "}")}, OXLINT),
    "nesting": Sample({"src/a.ts": text("export function deep(a: boolean): number {", "  if (a) {", "    if (a) {",
                                        "      if (a) {", "        if (a) {", "          if (a) {",
                                        "            return 1;", "          }", "        }", "      }", "    }", "  }",
                                        "  return 0;", "}")}, OXLINT),
    "complexity": Sample({"src/a.ts": text("export function branchy(x: number): number {",
                                           *(f"  if (x === {i}) {{ return {i}; }}" for i in range(12)),
                                           "  return x;", "}")}, OXLINT),
    "nested_ternary": Sample({"src/a.ts": text("export function f(x: number): number {",
                                               "  return x > 0 ? 1 : x < 0 ? 2 : 3;", "}")}, OXLINT),
    "type_lines": Sample({"src/a.ts": "export class Big {\n" + repeated("  m{i}() { return this; }", 260) + "}\n"},
                         RULES),
    "duplicate_lines": Sample({"src/b.ts": "export function two(values: number[], offsets: number[], scale: number)"
                                          ": void {\n" + CLONE + "}\n"}, ("jscpd",),
                              base={"src/a.ts": "export function one(values: number[], offsets: number[], scale: number)"
                                                ": void {\n" + CLONE + "}\n"}),
    "dead_code": Sample({"src/util.ts": HELPER + "\n\nexport function orphan(): number {\n  return 2;\n}\n"},
                        ("jscpd",), base={"src/main.ts": 'import { helper } from "./util";\n\nconsole.log(helper());\n',
                                          "src/util.ts": HELPER + "\n"}),
    "suppression": Sample({"src/a.ts": f"{SUPPRESS}\nexport const x: number = 'a' as unknown as number;\n"}, OXLINT),
    "swallowed_error": Sample({"src/a.ts": text("export function f(g: () => void): void {", "  try {", "    g();",
                                                "  } catch (e) {}", "}")}, OXLINT),
    "commented_code": Sample({"src/a.ts": "// const x = compute(1, 2);\nexport const y = 1;\n"}, RULES),
    "unused_params": Sample({"src/a.ts": text("export function f(a: number, unused: string): number {",
                                              "  return a;", "}")}, OXLINT),
    "magic_numbers": Sample({"src/a.ts": text("export function f(x: number): number {", "  return x * 86400;", "}")},
                            OXLINT),
    "debug_output": Sample({"src/a.ts": text("export function f(x: number): number {", "  console.log(x);",
                                             "  return x;", "}")}, OXLINT),
    "todo": Sample({"src/a.ts": f"{TODO}\nexport const x = 1;\n"}, OXLINT),
    "type_escape": Sample({"src/a.ts": text("export function f(a: any): number {", "  return a;", "}")}, OXLINT),
    "globals": Sample({"src/a.ts": text("let counter = 0;", "export function bump(): number {", "  counter += 1;",
                                        "  return counter;", "}")}, RULES),
    "bool_params": Sample({"src/a.ts": text("export function f(a: number, verbose: boolean): number {",
                                            "  return verbose ? a : 0;", "}")}, RULES),
    "broad_test_asserts": Sample({"src/a.test.ts": text('test("t", () => {', "  expect(() => f()).toThrow();", "});")},
                                 OXLINT),
    "broad_catch": Sample({"src/a.ts": text("export function f(a: () => void): void {", "  try { a(); } catch (e) { a(); }",
                                            "}")}, RULES),
    "missing_docs": Sample({"src/a.ts": text("export function fresh(): number {", "  return 2;", "}")}, RULES),
    "import_cycle": Sample({"src/a.ts": 'import { b } from "./b";\nexport const a = b;\n'}, OXLINT, base=CYCLE),
    "folder_cycle": Sample({"src/auth/login.ts": 'import { s } from "../ui/view";\nexport const v = s;\n'},
                           ("depcruise",), base=LAYERS),
    "skipped_test": Sample({"src/a.test.ts": f"export {{}};\n{SKIP}('a', () => {{}});\n"},
                           base={"src/a.test.ts": "export {};\n"}),
    "untested_file": Sample({"src/fresh.ts": repeated("export const x{i} = {i};", 30)}),
    "deprecated_api": Sample({"src/main.ts": text('import { oldFn } from "./lib.js";', "", "export function first(): number {",
                                                  "  return oldFn(1);", "}")}, ("oxlint", "tsgolint"),
                             base={"src/lib.ts": OLD_API}),
}


class TypeScriptMatrix(matrix.MatrixCase):
    SCAFFOLD = SCAFFOLD
    SAMPLES = SAMPLES
