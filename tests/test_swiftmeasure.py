"""What broom reads from Swift source itself: the blanking of comments and strings, how deep control flow nests, a
catch that never looks at its error and a private name nothing uses. None of it needs a tool."""

from __future__ import annotations


from support import BroomCase

from broom.swiftmeasure import blank, broad_catches, nesting, unused_private


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


class SwiftMeasureTest(BroomCase):
    def test_strings_and_comments_hold_no_braces(self) -> None:
        src = text('let a = "x { \\(f("}")) y"', 'let b = #"raw \\"{ \\#(g(")")) }"#', 'let c = """', "  { \\(x) }",
                   '  """', "/* outer /* inner { */ still } */", "// {", "let d = 1")
        code = blank(src)
        self.assertNotIn("{", code)
        self.assertNotIn("}", code)
        self.assertEqual(code.count("\n"), src.count("\n"), "lines stay where they were")
        self.assertIn("let d = 1", code)

    def test_nesting_counts_control_flow_in_its_function(self) -> None:
        code = blank(text("func deep(_ a: Bool) -> Int {", "    if a {",
                          "        for x in xs where xs.contains(where: { $0 > 1 }) {",
                          "            if a { } else {", "                switch a { default: return 1 }", "            }",
                          "        }", "    }", "    return 0", "}", "func flat() {", "    if a { }", "}"))
        self.assertEqual(nesting(code), {(1, "deep"): 4, (11, "flat"): 1}, "a closure argument and an else add none")

    def test_a_catch_is_broad_when_its_body_ignores_the_error(self) -> None:
        code = blank(text("func f() {", "    do { try g() } catch { log(\"x\") }", "    do { try g() } catch { log(error) }",
                          "    do { try g() } catch let e { throw e }", "    do { try g() } catch _ { h() }",
                          "    do { try g() } catch {}", "    do { try g() } catch MyError.x { h() }", "}"))
        self.assertEqual(broad_catches(code), [2, 5])

    def test_a_private_name_used_nowhere_else_is_dead(self) -> None:
        src = text("private func helper() {}", "private var used = 1", "@objc private func tapped() {}", "@IBAction",
                   "private func act() {}", "private enum CodingKeys {}", "fileprivate let lonely = used")
        self.assertEqual(unused_private(src), [(1, "func helper"), (7, "let lonely")])

