"""What broom reads from Swift's syntax tree, as swiftc parses it: how deep control flow nests, a catch that never
looks at its error, a ternary in a ternary and a file-level var. Each case holds what a text pattern got wrong: a
brace or a `catch` in a raw or multi-line string, an `else if`, an attribute the old patterns never saw."""

from __future__ import annotations

from test_swifttree import SwiftTreeCase, text

from broom.swiftmeasure import broad_catches, function_spans, globals_in, nested_ternaries, nesting, span_from
from broom.swiftkit import open_text


class SwiftMeasureTest(SwiftTreeCase):
    def test_nesting_counts_control_flow_in_its_function(self) -> None:
        tree = self.tree(text("func deep(_ a: Bool) -> Int {", "    if a {",
                              "        for x in xs where xs.contains(where: { $0 > 1 }) {",
                              "            if a { } else {", "                switch a { default: return 1 }",
                              "            }", "        }", "    }", "    return 0", "}", "func flat() {", "    if a { }",
                              "}"))
        self.assertEqual(nesting(tree), {(1, "deep"): 4, (11, "flat"): 1}, "a closure argument and an else add none")

    def test_a_brace_in_a_string_and_an_else_if_add_no_depth(self) -> None:
        tree = self.tree(text("@concurrent func f(_ a: Int) async -> Int {",
                              '    let s = #"raw { if a { while b { "#', '    let m = """', "      { { {", '      """',
                              "    if a == 1 { return 1 } else if a == 2 { return 2 } else if a == 3 { return 3 }",
                              "    return s.count + m.count", "}"))
        self.assertEqual(nesting(tree), {(1, "f"): 1})

    def test_a_function_inside_one_and_an_accessor_are_read_on_their_own(self) -> None:
        tree = self.tree(text("struct S {", "    var x: Int { if a { return 1 }; return 2 }", "    init() {",
                              "        func inner() { while a { if b {} } }", "        if a {}", "    }", "}"))
        self.assertEqual(nesting(tree), {(2, "x"): 1, (3, "init"): 1, (4, "inner"): 2})

    def test_a_function_takes_the_lines_from_its_row_through_its_closing_brace(self) -> None:
        tree = self.tree(text("struct S {", "    func outer() {", "        func inner() {", "            work()", "        }",
                              "        work()", "    }", "    init() {", "    }", "}"))
        spans = function_spans(tree)
        self.assertEqual([span_from(spans, line) for line in (2, 3, 8, 1)], [6, 3, 2, 0],
                         "the innermost function that holds the row's line; none for a type")

    def test_a_catch_is_broad_when_its_body_ignores_the_error(self) -> None:
        tree = self.tree(text("func f() {", '    do { try g() } catch { log("x") }', "    do { try g() } catch { log(error) }",
                              "    do { try g() } catch let e { throw e }", "    do { try g() } catch _ { h() }",
                              "    do { try g() } catch {}", "    do { try g() } catch MyError.x { h() }",
                              "    do { try g() } catch let e as MyError { h() }",
                              "    do { try g() } catch where retry { h() }",
                              '    do { try g() } catch { log("catch { error }") }', "}"))
        self.assertEqual(broad_catches(tree), [2, 5, 10], "an error named in a string is no use of it")

    def test_a_ternary_in_a_ternary(self) -> None:
        tree = self.tree(text("let a = x ? (y ? 1 : 2) : 3", "let b = x ? 1 : y ? 2 : 3", "let c = f(x ? 1 : 2) ? 3 : 4",
                              "v[x ? 0 : 1] = y ? 1 : 2", 'let d = "x ? y ? 1 : 2 : 3"', "let e = a?.b ?? 0",
                              "let f = (x ? 1 : 2) + (y ? 3 : 4)"))
        self.assertEqual(nested_ternaries(tree), [1, 2, 3])

    def test_a_ternary_has_the_line_of_its_own_expression(self) -> None:
        src = text("func f(x: Bool, y: Bool) {", "    let x1 = x", "    log(x1,", "        x ? (y ? 1 : 2) : 3)", "}")
        tree = self.tree(src)
        self.assertEqual(nested_ternaries(tree), [1], "without SourceKit, the line of the statement around it")
        source = open_text(src)
        if source is None:
            self.skipTest("sourcekitd missing")
        self.assertEqual(nested_ternaries(tree, source), [4])

    def test_a_file_level_var_is_a_global_outside_main_swift(self) -> None:
        src = text("var counter = 0", "let limit = 1", "struct S {", "    var x = 0", "    static var shared = S()",
                   "}", "private var hidden = 2")
        self.assertEqual(list(globals_in(self.tree(src))), [1, 7])
        self.assertEqual(list(globals_in(self.tree(src, "main.swift"))), [])
