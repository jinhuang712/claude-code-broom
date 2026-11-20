"""Smells read from a syntax tree by ast-grep: a rule matches nodes and never text, and a missing ast-grep says so."""

from __future__ import annotations

import shutil
import unittest
from unittest import mock

from support import BroomCase

from broom import syntax

RULE = """id: rust-static-mut
language: rust
message: a mutable static
metadata: {smell: globals}
rule:
  pattern: "static mut $N: $T = $V;"
"""


class SyntaxTest(BroomCase):
    def config_path(self):
        return self.tmp / "sg" / "sgconfig.yml"

    def config(self):
        rules = self.tmp / "sg" / "rules"
        rules.mkdir(parents=True)
        (rules / "static.yml").write_text(RULE)
        (self.tmp / "sg" / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
        return syntax.Rules(self.tmp / "sg" / "sgconfig.yml")

    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_a_rule_matches_the_node_and_not_the_same_text_in_a_string(self) -> None:
        src = self.tmp / "src"
        src.mkdir()
        (src / "m.rs").write_text('static mut X: i32 = 3;\nfn main() {\n    let s = "static mut Y: i32 = 4;";\n}\n')
        notes: list = []
        (m,) = syntax.matches(src, ["m.rs"], notes, 30, self.config())
        self.assertEqual((m.file, m.line, m.lines, m.smell, m.caught["N"]), ("m.rs", 1, 1, "globals", "X"))
        self.assertEqual(notes, [])
        narrowed = syntax.Rules(self.config_path(), only="^other-")
        self.assertEqual(syntax.matches(src, ["m.rs"], notes, 30, narrowed), [], "a run applies only the rules it names")

    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_a_line_separator_inside_a_match_keeps_it_one_match(self) -> None:
        src = self.tmp / "src"
        src.mkdir()
        (src / "m.rs").write_text('static mut X: &str = "a\u2028b\u0085c";\n')
        notes: list = []
        self.assertEqual([m.caught["N"] for m in syntax.matches(src, ["m.rs"], notes, 30, self.config())], ["X"])

    def test_without_ast_grep_nothing_is_read_and_a_note_says_so(self) -> None:
        notes: list = []
        with mock.patch.object(shutil, "which", return_value=None):
            self.assertEqual(syntax.matches(self.tmp, ["m.rs"], notes, 30), [])
        self.assertEqual(notes, [syntax.MISSING])

    def test_broom_own_rules_parse(self) -> None:
        if not shutil.which("ast-grep"):
            self.skipTest("ast-grep missing")
        (self.tmp / "m.go").write_text("package m\n")
        notes: list = []
        syntax.matches(self.tmp, ["m.go"], notes, 30)
        self.assertEqual([n for n in notes if n.startswith("failed:")], [], "every rule in defaults/sg parses")


    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_a_region_the_grammar_cant_read_is_left_out_with_a_note_in_every_language(self) -> None:
        broken = {"m.go": "package m\n\nfunc F( {\n// TODO: x\n",
                  "m.ts": "// TODO: a\nconst x = ;\n", "m.js": "// TODO: a\nconst x = ;\n",
                  "m.tsx": "// TODO: a\nconst x = ;\n", "m.css": "/* TODO: a */\na { color: red; }}}\n"}
        for name, text in broken.items():
            (self.tmp / name).write_text(text)
        notes: list = []
        found = syntax.parsed(syntax.by_file(syntax.matches(self.tmp, list(broken), notes, 30,
                                                            syntax.Rules(only="unparsed$")), list(broken)), notes)
        self.assertEqual(sorted(n.split()[3] for n in notes), sorted(broken), notes)
        self.assertEqual([m for ms in found.values() for m in ms], [], "the region itself is no finding")


if __name__ == "__main__":
    unittest.main()
