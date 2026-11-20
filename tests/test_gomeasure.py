"""What broom reads from Go source itself: a type's length with its methods, a `recover()` whose value is dropped and
a testify assertion any error passes, each read from the syntax tree by ast-grep. None of it needs golangci-lint, so
none of these tests do. Sample code is a list of lines, so that a handler of it never stands in this file as one."""

from __future__ import annotations

import json
import shutil
import unittest
from typing import List, Tuple

from support import BroomCase

from broom.gomeasure import type_sizes
from broom.syntax import matches
from broom.smells import find_smells

METRICS = ("type_lines", "broad_catch", "broad_test_asserts")


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


def method(type_name: str, name: str, lines: int) -> List[str]:
    """A method of `type_name` that is `lines` lines long."""
    return [f"func (t *{type_name}) {name}() int {{", *["\tx++"] * (lines - 2), "}", ""]


HEAD = ("package a", "", "type Big struct {", "\tx int", "}", "")
BIG = text(*HEAD, *method("Big", "A", 100), *method("Big", "B", 100))
BIGGER = BIG + text(*method("Big", "C", 60))
SMALL = text(*HEAD, *method("Big", "A", 20))
SMALLER = text(*HEAD, *method("Big", "A", 20), "func (t *Big) One() int { return 1 }")
FN = ("package a", "", "func f() {", "\tdefer func() {", "\t\tX", "\t}()", "}")
ERR = "\tassert.Error(t, err)"


def with_line(row: str) -> str:
    """A Go function with `row` in its deferred closure."""
    return text(*(row if line == "\t\tX" else line for line in FN))


@unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
class GoTextCase(BroomCase):
    def changed(self, rel: str, before: str, after: str) -> List[Tuple[str, str, List[int]]]:
        """The (smell, key, added lines) a change from `before` to `after` of the file `rel` makes."""
        r = self.repo({rel: before, ".broom.json": json.dumps({"smells_off": ["dead_code"]})})
        (r / rel).write_text(after)
        found, _ = find_smells(r, [r / rel], "HEAD")
        return [(s.metric, s.key, s.added) for s in found if s.metric in METRICS]


class TypeLinesTest(GoTextCase):
    def test_a_change_that_pushes_a_type_with_its_methods_past_the_limit_is_a_hint_keyed_by_its_name(self) -> None:
        found = [f for f in self.changed("a.go", BIG, BIGGER) if f[0] == "type_lines"]
        self.assertEqual([f[:2] for f in found], [("type_lines", "Big")])

    def test_a_short_type_is_quiet(self) -> None:
        self.assertEqual(self.changed("a.go", SMALL, SMALLER), [])

    def sizes(self, body: str) -> dict:
        """The (first line, lines) of each type in the Go file `body`, by name."""
        (self.tmp / "a.go").write_text(body)
        notes: list = []
        found = type_sizes(matches(self.tmp, ["a.go"], notes, 30))
        self.assertEqual(notes, [])
        return {name: size for (_, name), size in found.items()}

    def test_a_one_line_method_counts_one_line(self) -> None:
        self.assertEqual(self.sizes(SMALLER)["Big"], [3, 3 + 20 + 1])

    def test_a_type_in_a_group_counts_and_a_brace_in_a_raw_string_ends_nothing(self) -> None:
        body = text("package a", "", "type (", "\tSmall int", "\tGrouped struct {", "\t\tx int", "\t}", ")", "",
                    "func (g Grouped) Raw() string {", "\treturn `", "}", "`", "}")
        self.assertEqual(self.sizes(body), {"Grouped": [5, 3 + 5]})

    def test_an_old_long_type_is_not_reported_as_touched(self) -> None:
        r = self.repo({"a.go": BIGGER, ".broom.json": json.dumps({"smells_off": ["dead_code"]})})
        (r / "a.go").write_text(BIGGER.replace("x++", "x--", 1))
        found, _ = find_smells(r, [r / "a.go"], "HEAD")
        self.assertEqual([s for s in found if s.metric == "type_lines"], [])


class RecoverTest(GoTextCase):
    def added(self, row: str) -> List[Tuple[str, str, List[int]]]:
        return [f for f in self.changed("a.go", with_line("\t\t_ = 1"), with_line(row)) if f[0] == "broad_catch"]

    def test_recover_alone_and_assigned_to_the_blank_name_are_hints_on_the_added_line(self) -> None:
        for row in ("\t\trecover()", "\t\t_ = recover()"):
            with self.subTest(row=row):
                self.assertEqual([f[2] for f in self.added(row)], [[5]])

    def test_a_recover_whose_value_is_used_or_in_a_comment_or_a_string_is_quiet(self) -> None:
        for row in ("\t\tif r := recover(); r != nil {\n\t\t\tlog(r)\n\t\t}", "\t\t// calls recover() here",
                    "\t\t/*\n\t\trecover()\n\t\t*/", "\t\t_ = `\n\t\trecover()\n\t\t`"):
            with self.subTest(row=row):
                self.assertEqual(self.added(row), [])

    def test_an_old_occurrence_stays_quiet_when_the_change_is_elsewhere(self) -> None:
        old = with_line("\t\trecover()")
        self.assertEqual(self.changed("a.go", old, old + "\nvar y = 1\n"), [])


class AnyErrorTest(GoTextCase):
    def asserted(self, rel: str, row: str) -> List[Tuple[str, str, List[int]]]:
        before = text("package a", "", "func TestA(t *testing.T) {", "\tx := 1", "}")
        after = text("package a", "", "func TestA(t *testing.T) {", "\tx := 1", row, "}")
        return [f for f in self.changed(rel, before, after) if f[0] == "broad_test_asserts"]

    def test_an_assertion_any_error_passes_is_a_hint_in_a_test_file(self) -> None:
        for row in (ERR, "\trequire.Panics(t, f)", "\ts.Require().Error(err)"):
            with self.subTest(row=row):
                self.assertEqual([f[2] for f in self.asserted("a_test.go", row)], [[5]])

    def test_an_assertion_that_says_which_error_a_plain_report_a_non_test_file_and_a_string_are_quiet(self) -> None:
        for rel, row in (("a_test.go", "\tassert.ErrorIs(t, err, e)"), ("a_test.go", '\tt.Error("no")'), ("a.go", ERR),
                         ("a_test.go", '\tmsg := "assert.Error(t, err)"')):
            with self.subTest(rel=rel, row=row):
                self.assertEqual(self.asserted(rel, row), [])

    def test_an_old_occurrence_stays_quiet_when_the_change_is_elsewhere(self) -> None:
        old = text("package a", "", "func TestA(t *testing.T) {", ERR, "}")
        self.assertEqual(self.changed("a_test.go", old, old + "\nvar y = 1\n"), [])


if __name__ == "__main__":
    unittest.main()
