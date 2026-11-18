"""Swift: the build check, SwiftLint's defaults, the formatters and sourcekit-lsp."""

from __future__ import annotations

import unittest
from pathlib import Path

from support import (
    HAS_SOURCEKIT, HAS_SWIFT, HAS_SWIFT_FORMAT, HAS_SWIFTFORMAT, HAS_SWIFTLINT, BroomCase,
)


CLT = "/Library/Developer/CommandLineTools"  # macOS's Command Line Tools, next to Xcode
SWIFT_PACKAGE = {
    "Package.swift": "// swift-tools-version: 5.9\nimport PackageDescription\n\nlet package = Package(\n"
                     '    name: "M",\n'
                     '    targets: [.target(name: "M"), .testTarget(name: "MTests", dependencies: ["M"])]\n)\n',
    "Sources/M/Math.swift": "public func add(_ a: Int, _ b: Int) -> Int {\n    a + b\n}\n",
    "Sources/M/Use.swift": "public func three() -> Int {\n    add(1, 2)\n}\n",
    "Tests/MTests/Checks.swift": "@testable import M\n\nlet checked = add(1, 2)\n",
    ".gitignore": ".build/\n",
}
SWIFT_BUGS = "func f(a: Any) -> Int {\n    let n = a as! Int\n    if n == n { return 1 }\n    return n\n}\n"


class SwiftTest(BroomCase):
    # Swift

    @unittest.skipUnless(HAS_SWIFT, "swift missing")
    def test_swift_signature_change_breaks_callers_in_other_files(self) -> None:
        r = self.repo(SWIFT_PACKAGE)
        (r / "Sources/M/Math.swift").write_text(SWIFT_PACKAGE["Sources/M/Math.swift"].replace(
            "_ b: Int) -> Int {\n    a + b", "_ b: Int, _ c: Int) -> Int {\n    a + b + c"))
        self.sh(r, "git", "add", "-A")
        reason = self.denied(self.commit(r, "git commit -m sig"))
        self.assertIn("swift build", reason)
        self.assertIn("Sources/M/Use.swift:2:", reason)
        self.assertIn("not in the changed files", reason)
        (r / "Sources/M/Use.swift").write_text("public func three() -> Int {\n    add(1, 2, 0)\n}\n")
        (r / "Tests/MTests/Checks.swift").write_text("@testable import M\n\nlet checked = add(1, 2, 0)\n")
        self.sh(r, "git", "add", "-A")
        self.assertEqual(self.denied(self.commit(r, "git commit -m fixed")), "")

    @unittest.skipUnless(HAS_SWIFT, "swift missing")
    def test_swift_build_compiles_the_tests_too(self) -> None:
        r = self.repo(SWIFT_PACKAGE)
        (r / "Tests/MTests/Checks.swift").write_text('@testable import M\n\nlet checked: String = add(1, 2)\n')
        self.sh(r, "git", "add", "-A")
        self.assertIn("Tests/MTests/Checks.swift:3:", self.denied(self.commit(r, "git commit -m t")))

    @unittest.skipUnless(HAS_SWIFT and Path(CLT, "usr/bin/swift").exists(), "no Command Line Tools to switch to")
    def test_without_xcode_the_sources_are_built_and_the_tests_left_out(self) -> None:
        r = self.repo({**SWIFT_PACKAGE, "Tests/MTests/Checks.swift": "import XCTest\n@testable import M\n"})
        self.env["DEVELOPER_DIR"] = CLT  # no XCTest or swift-testing there
        (r / "Sources/M/Use.swift").write_text("// three\n" + SWIFT_PACKAGE["Sources/M/Use.swift"])
        self.sh(r, "git", "add", "-A")
        out = self.commit(r, "git commit -m doc")
        self.assertEqual(self.denied(out), "", "a missing test framework is no error in the code")
        self.assertIn("left the tests out", out["hookSpecificOutput"]["additionalContext"])
        (r / "Sources/M/Use.swift").write_text("public func three() -> Int {\n    add(1, 2, 3)\n}\n")
        self.sh(r, "git", "add", "-A")
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("Sources/M/Use.swift:2:", reason, "the sources are still built")
        self.assertNotIn("no such module", reason)

    @unittest.skipUnless(HAS_SWIFTLINT, "swiftlint missing")
    def test_swiftlint_defaults_find_bugs_not_style(self) -> None:
        r = self.repo({"App/App.xcodeproj/project.pbxproj": "// !$*UTF8*$!\n", "README.md": "app\n"})
        (r / "App/Sources").mkdir(parents=True)
        (r / "App/Sources/Parse.swift").write_text(SWIFT_BUGS)  # an Xcode app: linted, not built
        (r / "Pods/Dep").mkdir(parents=True)
        (r / "Pods/Dep/Dep.swift").write_text(SWIFT_BUGS)
        self.sh(r, "git", "add", "-A")
        reason = self.denied(self.commit(r, "git commit -m app"))
        self.assertIn("App/Sources/Parse.swift:2:15  force_cast", reason)
        self.assertIn("App/Sources/Parse.swift:3:8  identical_operands", reason)
        self.assertIn("blocked: 3 issue(s)", reason, "two lints and a type_escape; no naming rules, nothing from Pods")

    @unittest.skipUnless(HAS_SWIFTLINT, "swiftlint missing")
    def test_a_projects_swiftlint_config_replaces_the_defaults(self) -> None:
        r = self.repo({".swiftlint.yml": "only_rules:\n  - identifier_name\nexcluded:\n  - Generated\n",
                       "README.md": "x\n"})
        for name in ("Sources/Parse.swift", "Generated/Model.swift"):
            (r / name).parent.mkdir(parents=True, exist_ok=True)
            (r / name).write_text(SWIFT_BUGS)
        self.sh(r, "git", "add", "-A")
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("identifier_name", reason)
        self.assertNotIn("force_cast", reason)
        self.assertNotIn("Generated/Model.swift", reason, "the project's excluded paths hold for files broom names")
        self.sh(r, "git", "commit", "-qm", "x")
        (r / "Generated/Model.swift").write_text(SWIFT_BUGS + "// regenerated\n")
        self.sh(r, "git", "add", "-A")
        self.assertEqual(self.commit(r, "git commit -m only-excluded"), {}, "nothing left to lint is no failure")

    @unittest.skipUnless(HAS_SWIFT_FORMAT, "swift-format missing")
    def test_swift_is_formatted_only_where_configured(self) -> None:
        ugly = "func f( ) -> Int {\nreturn  1\n}\n"
        r = self.repo({"README.md": "x\n", "a.swift": "let a = 1\n"})
        (r / "b.swift").write_text(ugly)
        self.sh(r, "git", "add", "-A")
        self.commit(r, "git commit -m b")
        self.assertEqual((r / "b.swift").read_text(), ugly, "no formatter config, no formatting")
        self.assertIn("added .swift-format", self.cli(r, "init").stdout)
        self.assertIn('"spaces": 4', (r / ".swift-format").read_text())
        self.sh(r, "git", "add", "-A")
        out = self.commit(r, "git commit -m b")
        self.assertIn("swift-format", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual((r / "b.swift").read_text(), "func f() -> Int {\n    return 1\n}\n")
        self.assertEqual(self.sh(r, "git", "diff", "--name-only"), "", "the formatted file was re-staged")

    @unittest.skipUnless(HAS_SWIFTFORMAT, "swiftformat missing")
    def test_a_projects_swiftformat_config_picks_swiftformat(self) -> None:
        r = self.repo({".swiftformat": "--indent 2\n", "README.md": "x\n"})
        (r / "a.swift").write_text("func f( ) -> Int {\nreturn  1\n}\n")
        self.sh(r, "git", "add", "-A")
        out = self.commit(r, "git commit -m a")
        self.assertIn("swiftformat", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual((r / "a.swift").read_text(), "func f() -> Int {\n  return 1\n}\n")

    SWIFT_TWO_UNITS = ("struct Card {\n    var body: String {\n        let a  =  \"x\"\n        return a\n    }\n\n"
                       "    func other() -> Int {\n        let b  =  2\n        return b\n    }\n}\n")

    @unittest.skipUnless(HAS_SOURCEKIT, "sourcekit-lsp or swift-format missing")
    def test_function_scope_with_sourcekit_lsp_counts_computed_properties(self) -> None:
        r = self.repo({".swift-format": '{"version": 1, "indentation": {"spaces": 4}}\n',
                       "Card.swift": self.SWIFT_TWO_UNITS})
        (r / "Card.swift").write_text(self.SWIFT_TWO_UNITS.replace("return a\n", "return a + \"\"\n"))
        out = self.cli(r, "fmt", "--scope", "function").stdout
        self.assertNotIn("no language server answered", out)
        text = (r / "Card.swift").read_text()
        self.assertIn('let a = "x"', text, "SwiftUI-style body is a unit, like a function")
        self.assertIn("let b  =  2", text, "the untouched method is not")

    def test_swift_function_kinds_include_properties(self) -> None:
        from broom.lsp import FUNCTION_KINDS, SWIFT_KINDS, outermost_functions

        def sym(kind: int, first: int, last: int, *children: dict) -> dict:
            return {"kind": kind, "children": list(children), "range": {
                "start": {"line": first - 1, "character": 0}, "end": {"line": last - 1, "character": 1}}}

        # struct (1-10) holding a computed property (2-5, with an accessor-local variable) and a method (7-9)
        symbols = [sym(23, 1, 10, sym(7, 2, 5, sym(13, 3, 3)), sym(6, 7, 9))]
        self.assertEqual(outermost_functions(symbols, SWIFT_KINDS), [(2, 5), (7, 9)])
        self.assertEqual(outermost_functions(symbols, FUNCTION_KINDS), [(7, 9)])

    def test_doctor_finds_swift_in_xcode_apps_and_packages(self) -> None:
        r = self.repo({"App/App/ContentView.swift": "let a = 1\n", "Packages/Core/Package.swift": "// p\n",
                       "Packages/Core/Sources/Core/Core.swift": "let b = 1\n", "Pods/Dep/Dep.swift": "let c = 1\n"})
        env = self.fake_path()
        self.config_dir({"enabledPlugins": {"swift-lsp@claude-plugins-official": True}})
        result = self.doctor(r, env)
        self.assertEqual(result["languages"]["swift"], [".", "Packages/Core"], "vendored Pods don't count")
        status = {(i["tool"], i["status"]): i for i in result["items"]}
        self.assertEqual(status["swiftlint", "missing"]["fix"], "brew install swiftlint")
        self.assertIn(("sourcekit-lsp", "missing"), status)
        self.assertIn(("swift", "missing"), status, "a package is built, so it needs swift")
        self.assertEqual(result["configure"], ["brew install swift-format", "broom init ."])
        self.assertIn("claude plugin disable swift-lsp@claude-plugins-official", result["fix"])
        self.assertIn("added .swift-format", self.cli(r, "init").stdout)

    def test_doctor_reports_a_broken_toolchain_shim(self) -> None:
        r = self.repo({"a.swift": "let a = 1\n"})
        fake = 'echo "xcrun: error: invalid active developer path (/Library/Developer/CommandLineTools)" >&2; exit 1'
        items = self.doctor(r, self.fake_path(fakes={"sourcekit-lsp": fake, "xcode-select": "exit 0"}))["items"]
        lsp = next(i for i in items if i["tool"] == "sourcekit-lsp")
        self.assertEqual(lsp["status"], "broken")
        self.assertIn("invalid active developer path", lsp["detail"])
        self.assertEqual(lsp["fix"], "xcode-select --install")

    def test_swift_6_colored_compiler_errors_are_read(self) -> None:
        from broom.langlint import ANSI, swift_errors

        colored = ("/p/Sources/M/Use.swift:2:15: \x1b[1;31merror: \x1b[1;39mextra argument in call\x1b[0;0m\n"
                   "\x1b[0;36m2 |\x1b[0;0m     add(1, 2, 3)\n")
        self.assertEqual(swift_errors(Path("/p"), "") + swift_errors(Path("/p"), colored), [], "colors hide them")
        found = swift_errors(Path("/p"), ANSI.sub("", colored))
        self.assertEqual([(i.line, i.msg) for i in found], [(2, "extra argument in call")])

    def test_swift_6_words_a_missing_test_framework_its_own_way(self) -> None:
        from broom.langlint import NO_TEST_FRAMEWORK, swift_errors

        row = "error: /p/Tests/MTests/Checks.swift:1:8 unable to resolve module dependency: 'XCTest'\n"
        found = swift_errors(Path("/p"), row)
        self.assertEqual([(i.line, i.col) for i in found], [(1, 8)])
        self.assertTrue(NO_TEST_FRAMEWORK.match(found[0].msg))
