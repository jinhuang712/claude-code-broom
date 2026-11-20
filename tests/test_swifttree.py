"""Swift's syntax tree as swiftc gives it: many files in one run, code it can't parse left out with a note, and the
JSON its writer breaks after an attributed type repaired."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from support import BroomCase

from broom.swiftmeasure import nesting
from broom.swifttree import Tree, parse


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


class SwiftTreeCase(BroomCase):
    def setUp(self) -> None:
        super().setUp()
        if not shutil.which("swiftc"):
            self.skipTest("swiftc missing")

    def tree(self, src: str, rel: str = "a.swift", notes: List[str] = None) -> Tree:
        """The tree swiftc reads from `src` as the file `rel`."""
        (self.tmp / rel).write_text(src)
        trees = parse(self.tmp, [rel], [] if notes is None else notes)
        return trees[rel]


class SwiftTreeTest(SwiftTreeCase):
    def test_code_swiftc_cant_parse_is_left_out_with_a_note(self) -> None:
        notes: List[str] = []
        tree = self.tree(text("func broken( {", "    if a { if b { } }", "}", "func fine() {", "    if a { }", "}"),
                         notes=notes)
        self.assertEqual(nesting(tree), {(4, "fine"): 1})
        self.assertTrue(tree.unread(2))
        self.assertTrue(any("can't parse a.swift:1" in n for n in notes), notes)

    def test_an_attributed_type_leaves_the_tree_whole(self) -> None:
        # swiftc 6.4 writes the JSON after `@Sendable () -> Void` with an object left open; the tree is repaired.
        tree = self.tree(text("struct S {", "    typealias Work = @Sendable () async -> Void", "    func f() {",
                              "        if a { for x in y { while z { if w { if v { } } } } }", "    }", "}"))
        self.assertEqual(nesting(tree), {(3, "f"): 5})

    def test_many_files_are_one_run(self) -> None:
        for n in range(3):
            (self.tmp / f"f{n}.swift").write_text(text(f"func f{n}() {{", "    if a { }", "}"))
        trees = parse(self.tmp, [f"f{n}.swift" for n in range(3)], [])
        self.assertEqual({rel: nesting(t) for rel, t in trees.items()},
                         {f"f{n}.swift": {(1, f"f{n}"): 1} for n in range(3)})
        self.assertEqual(Path(trees["f1.swift"].rel).name, "f1.swift")
