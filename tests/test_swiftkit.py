"""SourceKit's view of Swift, through sourcekitd: its comments, run over the lines that follow one another, and a
string that holds `//` none of them."""

from __future__ import annotations

from support import BroomCase

from broom.swiftkit import SwiftFile, comments, library, open_text


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


class SourceKitCase(BroomCase):
    def setUp(self) -> None:
        super().setUp()
        if library() is None:
            self.skipTest("sourcekitd missing")

    def read(self, *rows: str) -> SwiftFile:
        """SourceKit's view of a file of `rows`."""
        f = open_text(text(*rows))
        assert f is not None
        return f


class SwiftKitTest(SourceKitCase):
    def test_comments_run_over_lines_that_follow_one_another(self) -> None:
        f = self.read("// one", "// two", "let x = 1  // trailing", "// three", "/// doc", 'let s = "// not one"',
                      "/* block", "   still */")
        self.assertEqual([(c.line, c.end, len(c.texts), c.slashes, c.alone) for c in comments(f)],
                         [(1, 2, 2, True, True), (3, 3, 1, True, False), (4, 4, 1, True, True), (7, 8, 1, False, True)])
