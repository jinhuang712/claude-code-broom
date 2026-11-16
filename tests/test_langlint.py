"""The linters' reports are read as data: JSON where the tool gives it, so what a message says can't confuse it."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import support  # noqa: F401  (puts lib on the path)
from broom.langlint import clippy_issues, golangci_issues, ruff_issues

ROOT = Path("/proj")


class ReportTests(unittest.TestCase):
    def test_ruff_findings_come_with_their_rule_and_a_syntax_error_without_one(self) -> None:
        out = json.dumps([
            {"code": "F401", "message": "`os` imported but unused", "filename": "/proj/a.py",
             "location": {"row": 3, "column": 8}},
            {"code": None, "message": "SyntaxError: Expected an expression", "filename": "/proj/b.py",
             "location": {"row": 1, "column": 5}},
        ])
        got = [(i.file.name, i.line, i.col, i.rule, i.msg) for i in ruff_issues(ROOT, out)]
        self.assertEqual(got, [("a.py", 3, 8, "F401", "`os` imported but unused"),
                               ("b.py", 1, 5, "syntax-error", "SyntaxError: Expected an expression")])
        self.assertEqual(ruff_issues(ROOT, ""), [])
        self.assertEqual(ruff_issues(ROOT, "not json"), [])

    def test_golangci_names_the_linter_even_when_the_message_ends_in_parentheses(self) -> None:
        # Read as text, "(Go 1.22+)" was taken for the linter's name and the finding for a compile error.
        out = json.dumps({"Issues": [
            {"FromLinter": "intrange", "Text": "for loop can be changed to use an integer range (Go 1.22+)",
             "Pos": {"Filename": "/proj/x.go", "Line": 397, "Column": 2}},
            {"FromLinter": "typecheck", "Text": "undefined: Foo",
             "Pos": {"Filename": "/proj/y.go", "Line": 5, "Column": 9}},
            {"FromLinter": "unused", "Text": "no position", "Pos": {}},
        ]})
        got = [(i.file.name, i.line, i.rule, i.hard) for i in golangci_issues(ROOT, out)]
        self.assertEqual(got, [("x.go", 397, "intrange", False), ("y.go", 5, "typecheck", True)])
        self.assertEqual(golangci_issues(ROOT, ""), [])
        self.assertEqual(golangci_issues(ROOT, "level=error msg=failed"), [])

    def test_clippy_messages_with_a_place_are_findings_and_the_rest_is_ignored(self) -> None:
        span = {"file_name": "src/lib.rs", "line_start": 7, "column_start": 4, "is_primary": True}
        rows = [
            json.dumps({"reason": "compiler-artifact", "target": {"name": "x"}}),
            json.dumps({"reason": "compiler-message", "message": {
                "level": "warning", "code": {"code": "clippy::needless_return"}, "message": "unneeded `return`",
                "spans": [span]}}),
            json.dumps({"reason": "compiler-message", "message": {
                "level": "error", "code": None, "message": "mismatched types", "spans": [span]}}),
            json.dumps({"reason": "compiler-message", "message": {
                "level": "warning", "code": None, "message": "`x` generated 1 warning", "spans": []}}),
            "not json at all",
        ]
        got = [(i.line, i.col, i.rule, i.hard) for i in clippy_issues(ROOT, "\n".join(rows), None, ROOT)]
        self.assertEqual(got, [(7, 4, "clippy::needless_return", False), (7, 4, "error", True)])


if __name__ == "__main__":
    unittest.main()
