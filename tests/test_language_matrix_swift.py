"""The language matrix for Swift: one sample per smell it can have, which leaves out the import cycle its modules
rule out, and the folder cycle broom doesn't read in Swift yet. See language_matrix."""

from __future__ import annotations

import language_matrix as matrix
from language_matrix import SWIFT_EXEMPT, Sample, repeated, text

# Pieces, so that this file holds no suppression or TODO of its own.
SUPPRESS = "// swift" + "lint:disable force_cast"
TODO = "// TO" + "DO: later"
LINT = ("swiftlint",)
TREE = ("swiftc",)  # read from the compiler's syntax tree and SourceKit's tokens
CLONE = repeated("    total += values[{i}] + offsets[{i}] * scale", 40)
PACKAGE = {
    "Package.swift": "// swift-tools-version: 5.9\nimport PackageDescription\n\n"
                     'let package = Package(name: "M", targets: [.target(name: "M")])\n',
    "Sources/M/Old.swift": text('@available(*, deprecated, message: "use fresh()")', "public func old() -> Int { 1 }"),
}


def nested(depth: int) -> list:
    """The lines of `depth` ifs nested in one another, each one indented under the one before."""
    return ([f"{'    ' * (n + 1)}if a {{" for n in range(depth)] + [f"{'    ' * (depth + 1)}return 1"]
            + [f"{'    ' * n}}}" for n in range(depth, 0, -1)])


def summed(name: str) -> str:
    """A function that adds up 40 values the same way, line by line."""
    return (f"func {name}(values: [Int], offsets: [Int], scale: Int) -> Int {{\n    var total = 0\n" + CLONE
            + "    return total\n}\n")


SAMPLES = {
    "function_lines": Sample({"a.swift": "func f() -> Int {\n    var x = 0\n" + repeated("    x += {i}", 58)
                              + "    return x\n}\n"}, LINT),
    "file_lines": Sample({"a.swift": repeated('let v{i} = "a"', 450)}),
    "params": Sample({"a.swift": text("func many(a: Int, b: Int, c: Int, d: Int, e: Int, f: Int, g: Int) -> Int {",
                                      "    a + b + c + d + e + f + g", "}")}, LINT),
    "nesting": Sample({"a.swift": text("func deep(_ a: Bool) -> Int {", *nested(5), "    return 0", "}")}, TREE),
    "complexity": Sample({"a.swift": text("func branchy(_ x: Int) -> Int {",
                                          *(f"    if x == {i} {{\n        return {i}\n    }}" for i in range(12)),
                                          "    return x", "}")}, LINT),
    "nested_ternary": Sample({"a.swift": text("func pick(a: Bool, b: Bool) -> Int {",
                                              "    a ? (b ? 1 : 2) : 3", "}")}, TREE),
    "type_lines": Sample({"a.swift": "struct Big {\n" + repeated("    let v{i} = {i}", 260) + "}\n"}, LINT),
    "duplicate_lines": Sample({"b.swift": summed("two")}, ("jscpd",), base={"a.swift": summed("one")}),
    "dead_code": Sample({"a.swift": text("struct A {", "    private func helper() -> Int { 1 }", "}")}, TREE),
    "suppression": Sample({"a.swift": text(SUPPRESS, "func f(a: Any) -> Int {", "    a as! Int", "}")}, LINT),
    "swallowed_error": Sample({"a.swift": text("func f(_ x: Int) {", "    if x > 1 {", "    }", "}")}, LINT),
    "commented_code": Sample({"a.swift": text("func f() -> Int {", "    // let x = compute(1, 2)", "    return 1", "}")},
                             TREE),
    "unused_params": Sample({"a.swift": text("func f(a: Int, unused: Int) -> Int {", "    a", "}")}, LINT),
    "magic_numbers": Sample({"a.swift": text("func f(_ x: Int) -> Int {", "    x * 86400", "}")}, LINT),
    "debug_output": Sample({"a.swift": text("func f() {", '    print("x")', "}")}, TREE),
    "todo": Sample({"a.swift": text(TODO, "func f() -> Int {", "    1", "}")}, LINT),
    "type_escape": Sample({"a.swift": text("func f(a: Any) -> Int {", "    a as! Int", "}")}, LINT),
    "globals": Sample({"a.swift": text("var counter = 0", "", "func bump() -> Int {", "    counter += 1",
                                       "    return counter", "}")}, TREE),
    "bool_params": Sample({"a.swift": text("func f(_ a: Int, _ verbose: Bool) -> Int {", "    verbose ? a : 0", "}")},
                          TREE),
    "broad_test_asserts": Sample({"Tests/ATests.swift": text("import XCTest", "", "final class ATests: XCTestCase {",
                                                             "    func testA() {",
                                                             "        XCTAssertThrowsError(try parse())", "    }",
                                                             "}")}, TREE),
    "broad_catch": Sample({"a.swift": text("func f() {", "    do {", "        try g()", "    } catch {",
                                           '        log("failed")', "    }", "}")}, TREE),
    "missing_docs": Sample({"a.swift": text("public func fresh() -> Int { 2 }")}, LINT),
    "skipped_test": Sample({"Tests/ATests.swift": text("import XCTest", "", "final class ATests: XCTestCase {",
                                                       "    func testA() throws {", '        throw XCTSkip("later")',
                                                       "    }", "}")},
                           TREE, base={"Tests/ATests.swift": "import XCTest\n"}),
    "untested_file": Sample({"fresh.swift": repeated("let c{i} = {i}", 30)}),
    "deprecated_api": Sample({"Sources/M/Use.swift": text("public func use() -> Int {", "    old()", "}")},
                             ("swiftc",), base=PACKAGE),
}


class SwiftMatrix(matrix.MatrixCase):
    EXEMPT = SWIFT_EXEMPT
    SAMPLES = SAMPLES
