"""What broom reads from SourceKit's tokens and structure of Swift: debug prints, unlabeled Bool parameters, broad
test asserts, skipped tests and private names nothing uses.
Each case holds what a text pattern got wrong: a call, a skip or a TODO in a string."""

from __future__ import annotations

from test_swiftkit import SourceKitCase, text

from broom.statscan import scan
from broom.swiftcalls import broad_asserts, file_smells, skips, test_cases, unsafe_uses, unused_private
from broom.testrot import skip_rows


class SwiftCallsTest(SourceKitCase):
    def test_a_debug_print_is_the_free_function_called(self) -> None:
        f = self.read("func f(printer: Printer) {", '    print("x")', '    let s = "print(y)"  // print(z)',
                      '    printer.print("x")', "    Swift.print(1)", "    NSLog(\"%d\",", "          2)", "}")
        self.assertEqual(file_smells(f), [(2, "debug_output"), (5, "debug_output"), (6, "debug_output")])

    def test_a_bool_parameter_with_no_label(self) -> None:
        f = self.read("func a(_ verbose: Bool) {}", "func b(verbose: Bool, _ n: Int) {}", "func c(_ on: Bool?) {}",
                      "struct S {", "    init(_ flag: Bool,", "         _ other: Bool) {}", "}",
                      "let k = { (_ x: Bool) in x }")
        self.assertEqual(file_smells(f), [(1, "bool_params"), (5, "bool_params"), (6, "bool_params")])

    def test_a_test_that_any_error_is_thrown(self) -> None:
        f = self.read("func t() throws {", "    XCTAssertThrowsError(try parse())",
                      "    XCTAssertThrowsError(try parse()) { e in check(e) }",
                      '    XCTAssertThrowsError(try parse(), "m", errorHandler: { _ in })',
                      "    #expect(throws: (any Error).self) { try g() }", "    #expect(throws: Error.self) { try g() }",
                      "    #require(throws: MyError.self) { try g() }", "    try check(throws: Error.self)", "}")
        self.assertEqual(list(broad_asserts(f)), [2, 5, 6])

    def test_a_skip_and_whether_a_condition_decides_it(self) -> None:
        f = self.read("import XCTest", "final class ATests: XCTestCase {", '    func testA() throws { throw XCTSkip("later") }',
                      "    func testB() throws { try XCTSkipIf(slow) }",
                      '    func testC() throws { guard fast else { throw XCTSkip("slow") } }',
                      '    func testD() { let s = "XCTSkip(" }', "}", '@Test(.disabled("flaky")) func e() {}',
                      "@Test(.disabled(if: slow)) func f() {}")
        self.assertEqual(list(skips(f)), [(3, False), (4, True), (5, True), (8, False), (9, True)])
        self.assertEqual(test_cases(f), 6)

    def test_a_private_name_used_nowhere_else_is_dead(self) -> None:
        f = self.read("private func helper() {}", "private var used = 1", "@objc private func tapped() {}",
                      "@IBAction", "private func act() {}", "private enum CodingKeys {}", "fileprivate let lonely = used",
                      "private struct Shape {}", "func draw(_ s: Shape) {}", "private(set) var count = 0",
                      'private let quoted = 1  // quoted', 'let s = "quoted"', "struct T {", "    private init() {}",
                      "    override private func viewDidLoad() {}", "}")
        self.assertEqual(unused_private(f), [(1, "func helper"), (7, "let lonely"), (11, "let quoted")])

    def test_unsafe_code_is_a_call_of_a_with_unsafe_function_or_a_pointer_type_by_name(self) -> None:
        rows = ("func f(d: Data, p: UnsafePointer<UInt8>) {", "    d.withUnsafeBytes { raw in _ = raw }",
                "    withUnsafePointer(to: &x) { _ in }", "    let a = UnsafeMutablePointer<Int>.allocate(capacity: 1)",
                '    let s = "withUnsafeBytes UnsafePointer"  // withUnsafeBytes UnsafeRawPointer',
                "    let unsafeCount = 1", "    let c: [UnsafeRawBufferPointer] = []", "}")
        self.assertEqual(unsafe_uses(self.read(*rows)), 5, "two calls and three types; no string, comment or name")
        self.assertEqual(scan("A.swift", "swift", text(*rows)).unsafe, 5)

    def test_skip_rows_and_stats_read_swift_from_its_tree(self) -> None:
        src = text("import XCTest", "// TO" + "DO: later", 'let s = "TO' + 'DO: not a comment"',
                   "// swift" + "lint:disable force_cast", 'let t = "swift' + 'lint:disable force_cast"',
                   "final class ATests: XCTestCase {", '    func testA() throws { throw XCTSkip("x") }',
                   "    func testB() throws { try XCTSkipIf(true) }", "}")
        rows = skip_rows({"Tests/ATests.swift": src, "Sources/A.swift": src})
        self.assertEqual([(r.rel, r.line) for r in rows], [("Tests/ATests.swift", 7)])
        facts = scan("Tests/ATests.swift", "swift", src)
        self.assertEqual((facts.cases, facts.skipped, facts.todos, len(facts.suppressions)), (2, 2, [2], 1))
