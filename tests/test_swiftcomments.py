"""Commented-out Swift code: a comment that swiftc parses as a statement of code. Prose that looks like code, and
prose that happens to parse, is none."""

from __future__ import annotations

import shutil

from test_swiftkit import SourceKitCase, text

from broom.swiftcomments import commented_code


class SwiftCommentsTest(SourceKitCase):
    def test_commented_code_is_a_comment_swiftc_parses_as_code(self) -> None:
        if not shutil.which("swiftc"):
            self.skipTest("swiftc missing")
        (self.tmp / "a.swift").write_text(text(
            "func f() -> Int {", "    // let x = compute(1, 2)", "", "    // This computes the total (see docs).",
            "    // Note: foo(bar)", "    // TODO: tidy this", "    // MARK: - Helpers", "    // if x is set, retry {see docs}",
            "    // swiftlint:disable force_cast", "    // https://example.com/x?y=1", "    // Done",
            "    // nil-checked (HomeFonts, cx-qpqs)", "    // [text](url)", "",
            "    // if x {", "    //     y()", "    // }", "", "    // x += 1", '    let s = "// let y = 2"  // return 3',
            "    return 1", "}"))
        self.assertEqual(commented_code(self.tmp, ["a.swift"]), [("a.swift", 2), ("a.swift", 15), ("a.swift", 19),
                                                                 ("a.swift", 20)])
