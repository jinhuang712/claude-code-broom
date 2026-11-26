"""The language matrix for Go: one sample per smell it can have, which leaves out the ternary and the package cycles
its compiler and syntax rule out. See language_matrix."""

from __future__ import annotations

import language_matrix as matrix
from language_matrix import GO_EXEMPT, Sample, repeated, text

# Pieces, so that this file holds no suppression or TODO of its own.
SUPPRESS = "//no" + "lint"
TODO = "// TO" + "DO: later"
SCAFFOLD = {"go.mod": "module example.com/m\n\ngo 1.22\n"}
LINT = ("golangci-lint",)
TYPED = ("golangci-lint", "go")  # the linters that need types build the module
TREE = ("ast-grep",)
CLONE = repeated("\ttotal += values[{i}] + offsets[{i}]*scale", 40)
TYPE_HEAD = ("package a", "", "type Big struct {", "\tx int", "}", "")


def method(name: str, lines: int) -> str:
    """A method of Big that is `lines` lines long."""
    return text(f"func (t *Big) {name}() int {{", *["\tt.x++"] * (lines - 2), "}", "")


SAMPLES = {
    "function_lines": Sample({"a.go": "package a\n\nfunc F() int {\n\tx := 0\n" + repeated("\tx += {i}", 58)
                              + "\treturn x\n}\n"}, LINT),
    "file_lines": Sample({"a.go": "package a\n\n" + repeated('const V{i} = "a"', 450)}),
    "params": Sample({"a.go": text("package a", "", "func Many(a, b, c, d, e, f, g int) int {",
                                   "\treturn a + b + c + d + e + f + g", "}")}, LINT),
    "nesting": Sample({"a.go": text("package a", "", "func Deep(a bool) int {", "\tif a {", "\t\tif a {", "\t\t\tif a {",
                                    "\t\t\t\tif a {", "\t\t\t\t\tif a {", "\t\t\t\t\t\treturn 1", "\t\t\t\t\t}",
                                    "\t\t\t\t}", "\t\t\t}", "\t\t}", "\t}", "\treturn 0", "}")}, LINT),
    "complexity": Sample({"a.go": text("package a", "", "func Branchy(x int) int {",
                                       *(f"\tif x == {i} {{\n\t\treturn {i}\n\t}}" for i in range(12)),
                                       "\treturn x", "}")}, LINT),
    "type_lines": Sample({"a.go": text(*TYPE_HEAD) + method("A", 100) + method("B", 100) + method("C", 60)}),
    "duplicate_lines": Sample({"b.go": "package a\n\nfunc Two(values, offsets []int, scale int) int {\n\ttotal := 0\n"
                                      + CLONE + "\treturn total\n}\n"}, ("jscpd",),
                              base={"a.go": "package a\n\nfunc One(values, offsets []int, scale int) int {\n\ttotal := 0\n"
                                            + CLONE + "\treturn total\n}\n"}),
    "dead_code": Sample({"a.go": text("package a", "", "func helper() int {", "\treturn 1", "}")}, TYPED),
    "suppression": Sample({"a.go": text("package a", "", "func F() int {", f"\treturn 1 {SUPPRESS}", "}")}, LINT),
    "swallowed_error": Sample({"a.go": text("package a", "", "func F(x int) {", "\tif x > 1 {", "\t}", "}")}, LINT),
    "commented_code": Sample({"a.go": text("package a", "", "func F() int {", "\t// x := compute(1, 2)",
                                           "\t// if x > 3 { return }", "\treturn 1", "}")}, TYPED),
    "unused_params": Sample({"a.go": text("package a", "", "func F(a, unused int) int {", "\treturn a", "}")}, LINT),
    "magic_numbers": Sample({"a.go": text("package a", "", "func F(x int) int {", "\treturn x * 86400", "}")}, LINT),
    "debug_output": Sample({"a.go": text("package a", "", 'import "fmt"', "", "func F() {", '\tfmt.Println("x")', "}")},
                           TREE),
    "todo": Sample({"a.go": text("package a", "", TODO, "func F() int {", "\treturn 1", "}")}, LINT),
    "type_escape": Sample({"a.go": text("package a", "", "func F(a interface{}) string {", "\treturn a.(string)", "}")},
                          LINT),
    "globals": Sample({"a.go": text("package a", "", "var counter int", "", "func Bump() int {", "\tcounter++",
                                    "\treturn counter", "}")}, TREE),
    "bool_params": Sample({"a.go": text("package a", "", "func F(a int, verbose bool) int {", "\tif verbose {",
                                        "\t\treturn a", "\t}", "\treturn 0", "}")}, LINT),
    "broad_test_asserts": Sample({"a_test.go": text("package a", "", "func TestA(t *testing.T) {", "\tx := 1",
                                                    "\tassert.Error(t, err)", "}")}),
    "broad_catch": Sample({"a.go": text("package a", "", "func F() {", "\tdefer func() {", "\t\trecover()", "\t}()", "}")}),
    "missing_docs": Sample({"a.go": text("package a", "", "func Fresh() int { return 2 }")}, LINT),
    "skipped_test": Sample({"a_test.go": text("package a", "", "func TestA(t *testing.T) {", '\tt.Skip("later")', "}")},
                           base={"a_test.go": "package a\n"}),
    "untested_file": Sample({"fresh.go": "package a\n\n" + repeated("const C{i} = {i}", 30)}),
    "deprecated_api": Sample({"a.go": text("package a", "", 'import "strings"', "", "func Title(s string) string {",
                                           "\treturn strings.Title(s)", "}")}, TYPED),
}


class GoMatrix(matrix.MatrixCase):
    EXEMPT = GO_EXEMPT
    SCAFFOLD = SCAFFOLD
    SAMPLES = SAMPLES
