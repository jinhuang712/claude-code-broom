"""Deprecated calls in Swift: the compiler's warnings read, and the targets of a package found from its manifest.
The type check itself is proven by the Swift language matrix."""

from __future__ import annotations

from pathlib import Path

from support import BroomCase

from broom.swiftcheck import deprecations, target_dir


class SwiftCheckTest(BroomCase):
    def test_only_deprecation_warnings_are_read(self) -> None:
        out = ("/p/Sources/M/Use.swift:2:5: warning: 'old()' is deprecated: use fresh [#DeprecatedDeclaration]\n"
               "/p/Sources/M/Use.swift:3:9: warning: variable 'x' was never used [#no-usage]\n"
               "/p/Sources/M/Use.swift:4:1: error: cannot find 'y' in scope\n")
        self.assertEqual(deprecations(out), [(Path("/p/Sources/M/Use.swift").resolve(), 2,
                                              "old() is deprecated: use fresh")])

    def test_a_target_lives_where_its_manifest_or_swiftpm_says(self) -> None:
        here = Path(__file__).parent
        self.assertEqual(target_dir(here, {"name": "M", "path": "Lib/M"}), here / "Lib/M")
        self.assertIsNone(target_dir(here, {"name": "Nowhere", "type": "test"}))

