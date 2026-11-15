"""Smells that need the project's real checkout: typed linters, module graphs. Only what the change adds counts."""

from __future__ import annotations

import shutil
import unittest

from support import HAS_GO, BroomCase

from broom.smells import find_smells

GO_MOD = "module example.com/x\n\ngo 1.22\n"
GO_CLEAN = 'package main\n\nimport "strings"\n\nfunc Upper(s string) string {\n\treturn strings.ToUpper(s)\n}\n'
GO_SMELLY = """package main

import (
	"fmt"
	"strings"
)

var counter int

func Upper(s string) string {
	fmt.Println("debug")
	// x := compute(1, 2)
	// if x > 3 { return }
	return strings.ToUpper(s)
}

func helper() int {
	return 1
}
"""


class RealTreeTest(BroomCase):
    def metrics(self, r, rel: str) -> list:
        found, _ = find_smells(r, [r / rel], "HEAD")
        return sorted((s.level, s.metric) for s in found)

    @unittest.skipUnless(HAS_GO, "go or golangci-lint missing")
    def test_go_smells_that_need_types_are_found_on_the_lines_a_change_adds(self) -> None:
        r = self.repo({"go.mod": GO_MOD, "main.go": GO_CLEAN})
        (r / "main.go").write_text(GO_SMELLY)
        self.assertEqual(self.metrics(r, "main.go"),  # `counter` and `helper` are both unused
                         [("block", "commented_code"), ("hint", "dead_code"), ("hint", "dead_code"),
                          ("hint", "debug_output"), ("hint", "globals")])

    @unittest.skipUnless(HAS_GO, "go or golangci-lint missing")
    def test_a_go_smell_the_change_did_not_add_stays_quiet(self) -> None:
        r = self.repo({"go.mod": GO_MOD, "main.go": GO_SMELLY})
        (r / "main.go").write_text(GO_SMELLY.replace('"debug"', '"debug twice"'))  # the line is edited, not new
        self.assertEqual([m for _, m in self.metrics(r, "main.go")], ["debug_output"], "the edited line only")
        (r / "main.go").write_text(GO_SMELLY + "\n// a note\n")  # a line far from every smell
        self.assertEqual(self.metrics(r, "main.go"), [])

    @unittest.skipUnless(shutil.which("oxlint"), "oxlint missing")
    def test_an_import_that_closes_a_ts_cycle_is_found_where_it_is_added(self) -> None:
        r = self.repo({"a.ts": "export const a = 1;\n", "b.ts": 'import { a } from "./a";\nexport const b = a;\n'})
        (r / "a.ts").write_text('import { b } from "./b";\nexport const a = b;\n')
        self.assertIn(("hint", "import_cycle"), self.metrics(r, "a.ts"))

    @unittest.skipUnless(shutil.which("oxlint"), "oxlint missing")
    def test_a_ts_cycle_that_was_there_before_stays_quiet(self) -> None:
        cycle = {"a.ts": 'import { b } from "./b";\nexport const a = b;\n',
                 "b.ts": 'import { a } from "./a";\nexport const b = a;\n'}
        r = self.repo(cycle)
        (r / "a.ts").write_text(cycle["a.ts"] + "export const other = 2;\n")
        self.assertNotIn("import_cycle", [m for _, m in self.metrics(r, "a.ts")])
