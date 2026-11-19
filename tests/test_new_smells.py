"""The two occurrence smells of the check-up checkpoint, on added lines and on old ones: `missing_docs`, public code
with no doc comment, and `broad_catch`, an error handler that catches every error. Sample code is a list of lines,
so that a handler of it never stands in this file as one."""

from __future__ import annotations

import json
import shutil
import unittest
from typing import List, Sequence, Tuple

from support import HAS_GO, HAS_PY, HAS_SWIFTLINT, BroomCase

from broom.config import SMELL_PRESENCE
from broom.smells import find_smells


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


DOCUMENTED = text('"""A module."""', "", "", "def old(x):", '    """Say what it is for."""', "    return x")
UNDOCUMENTED = text('"""A module."""', "", "", "def old(x):", "    return x")
WITH_NEW = UNDOCUMENTED + text("", "", "def fresh(x):", "    return x", "", "", "def _helper(x):", "    return x",
                               "", "", "class Thing:", "    def method(self):", "        return 1")
HEAD = ("def risky(x):", '    """Parse x."""', "    try:", "        return int(x)")
CATCH_ALL = text(*HEAD, "    except Exception:", "        return 0")
BARE = text(*HEAD, "    except:", "        return 0")
NARROW = text(*HEAD, "    except ValueError:", "        return 0")
RERAISED = text(*HEAD, "    except Exception:", "        raise")


# Written in two pieces: this file would otherwise hold a suppression itself.
DIRECTIVE = "// eslint" + "-disable-next-line no-console"


class NewSmellCase(BroomCase):
    def changed(self, rel: str, before: str, after: str, off: Sequence[str] = ()) -> List[Tuple[str, List[int]]]:
        """The (smell, added lines) a change from `before` to `after` of the file `rel` makes worse, for the two smells
        of this file."""
        r = self.repo({rel: before, ".broom.json": json.dumps({"smells_off": list(off)})})
        (r / rel).write_text(after)
        found, _ = find_smells(r, [r / rel], "HEAD")
        return [(s.metric, s.added) for s in found if s.metric in ("missing_docs", "broad_catch")]


@unittest.skipUnless(HAS_PY, "ruff missing")
class MissingDocsTest(NewSmellCase):
    def test_it_is_a_hint_and_an_occurrence_smell(self) -> None:
        self.assertEqual(SMELL_PRESENCE["missing_docs"], "hint")
        self.assertEqual(SMELL_PRESENCE["broad_catch"], "hint")

    def test_public_code_a_change_adds_without_a_docstring_is_found(self) -> None:
        found = self.changed("pkg/a.py", DOCUMENTED, DOCUMENTED + text("", "", "def fresh(x):", "    return x"))
        self.assertEqual(found, [("missing_docs", [9])])

    def test_a_new_function_a_class_and_its_method_count_and_a_private_helper_does_not(self) -> None:
        found = self.changed("pkg/a.py", UNDOCUMENTED, WITH_NEW)
        self.assertEqual(found, [("missing_docs", [8, 16, 17])], "fresh, Thing and Thing.method; not _helper")

    def test_a_new_module_with_no_docstring_counts_as_one(self) -> None:
        r = self.repo({"README.md": "x\n"})
        (r / "pkg").mkdir()
        (r / "pkg/new.py").write_text(text("VALUE = 1"))
        found, _ = find_smells(r, [r / "pkg/new.py"], "HEAD")
        self.assertEqual([(s.metric, s.level, s.added) for s in found if s.metric == "missing_docs"],
                         [("missing_docs", "hint", [1])])

    def test_old_code_with_no_docstring_stays_quiet_when_the_change_is_elsewhere(self) -> None:
        found = self.changed("pkg/a.py", UNDOCUMENTED, UNDOCUMENTED.replace("return x", "return x + 1"))
        self.assertEqual(found, [])
        moved = self.changed("pkg/a.py", UNDOCUMENTED, UNDOCUMENTED.replace("\n\n\ndef", "\n\nVALUE = 1\n\n\ndef"))
        self.assertEqual(moved, [], "a function that only moved down is old")

    def test_a_documented_function_and_a_test_need_no_comment(self) -> None:
        self.assertEqual(self.changed("pkg/a.py", DOCUMENTED, DOCUMENTED.replace("return x", "return x + 1")), [])
        self.assertEqual(self.changed("tests/test_a.py", "X = 1\n", text("X = 1", "", "", "def test_it():", "    pass")),
                         [])

    def test_smells_off_turns_it_off(self) -> None:
        added = DOCUMENTED + text("", "", "def fresh(x):", "    return x")
        self.assertEqual(self.changed("pkg/a.py", DOCUMENTED, added, off=["missing_docs"]), [])


@unittest.skipUnless(HAS_PY, "ruff missing")
class BroadCatchTest(NewSmellCase):
    def test_a_handler_that_catches_every_error_is_found_bare_or_not(self) -> None:
        for name, code in (("except Exception", CATCH_ALL), ("a bare except", BARE)):
            with self.subTest(name):
                self.assertEqual(self.changed("pkg/a.py", "X = 1\n", "X = 1\n\n\n" + code), [("broad_catch", [8])])

    def test_a_handler_for_the_expected_error_or_one_that_re_raises_is_quiet(self) -> None:
        self.assertEqual(self.changed("pkg/a.py", "X = 1\n", "X = 1\n\n\n" + NARROW), [])
        self.assertEqual(self.changed("pkg/a.py", "X = 1\n", "X = 1\n\n\n" + RERAISED), [])

    def test_an_old_handler_stays_quiet_and_so_does_a_change_elsewhere(self) -> None:
        self.assertEqual(self.changed("pkg/a.py", CATCH_ALL, CATCH_ALL.replace("return 0", "return -1")), [])

    def test_a_second_handler_in_the_file_counts(self) -> None:
        second = CATCH_ALL.replace("risky", "again")
        self.assertEqual(self.changed("pkg/a.py", CATCH_ALL, CATCH_ALL + "\n\n" + second), [("broad_catch", [13])])

    def test_smells_off_turns_it_off(self) -> None:
        self.assertEqual(self.changed("pkg/a.py", "X = 1\n", "X = 1\n\n\n" + CATCH_ALL, off=["broad_catch"]), [])


class OtherLanguagesTest(NewSmellCase):
    @unittest.skipUnless(HAS_GO, "go or golangci-lint missing")
    def test_an_exported_go_function_with_no_comment_counts_and_an_unexported_one_does_not(self) -> None:
        before = text("package a", "", "// Old does it.", "func Old() int { return 1 }")
        after = before + text("", "func Fresh() int { return 2 }", "", "func private() int { return 3 }", "",
                              "// Other is not in the form revive likes, but it has a comment.", "func Other() {}")
        found = self.changed("go/a.go", before, after)
        self.assertEqual([m for m, _ in found], ["missing_docs"])
        self.assertEqual(found[0][1], [6])

    @unittest.skipUnless(shutil.which("oxlint") and shutil.which("node"), "oxlint or node missing")
    def test_an_exported_ts_function_or_class_with_no_comment_counts(self) -> None:
        before = text("/** Old. */", "export function old(): number {", "  return 1;", "}")
        after = before + text(
            "", "export function fresh(): number {", "  return 2;", "}",  # 6: no comment
            "", "// A line comment says what it is for.", "export const noted = (): number => 3;",
            "", "export const bare = (): number => 4;",  # 13: no comment
            "", DIRECTIVE, "export class Loud {}",  # 16: a directive is no comment
            "", "function local(): number {", "  return 5;", "}",
            "", "export function over(a: string): void;", "export function over(a: number): void;",
            "export function over(a: unknown): void {", "  void a;", "}",  # overloads: left alone
            "", "export const value = 6;", "export interface Shape {", "  a: number;", "}")
        self.assertEqual(self.changed("src/a.ts", before, after), [("missing_docs", [6, 13, 16])])
        self.assertEqual(self.changed("src/a.test.ts", before, after), [], "a test owes no doc comment")

    @unittest.skipUnless(HAS_SWIFTLINT, "swiftlint missing")
    def test_a_public_swift_declaration_with_no_comment_counts_and_an_internal_one_does_not(self) -> None:
        before = text("/// Old.", "public func old() {}")
        after = before + text("", "public func fresh() {}", "", "func hidden() {}")
        self.assertEqual(self.changed("a.swift", before, after), [("missing_docs", [4])])

    @unittest.skipUnless(shutil.which("oxlint") and shutil.which("node"), "oxlint or node missing")
    def test_a_ts_handler_that_ignores_the_error_and_throws_nothing_is_found(self) -> None:
        before = "export const x = 1;\n"
        after = before + text(
            "", "/** Fresh. */", "export function fresh(a: () => void, p: Promise<number>): void {",
            "  try { a(); } catch (e) { a(); }",  # 5: never mentions e
            "  try { a(); } catch { a(); }",  # 6: no parameter
            "  try { a(); } catch (e) { }",  # empty: no-empty's
            "  try { a(); } catch (e) { /* ignored */ }",  # comment only
            "  try { a(); } catch (e) { console.error(e); }",
            "  try { a(); } catch (e) { if (e instanceof RangeError) a(); }",
            "  try { a(); } catch ({ code }) { a(); }",
            "  try { a(); } catch (e) { throw new Error('wrapped'); }",
            "  p.catch(() => {});",  # 13: empty body counts
            "  p.catch((e) => 0);",  # 14
            "  p.catch(function () { return 1; });",  # 15
            "  p.then((v) => v).catch((err) => { a(); });",  # 16
            "  p.catch(console.error);",
            "  p.catch((e) => console.error(e));",
            "  p.catch(() => { throw new Error('wrapped'); });",
            "}")
        self.assertEqual(self.changed("src/a.ts", before, after), [("broad_catch", [5, 6, 13, 14, 15, 16])])

    @unittest.skipUnless(shutil.which("oxlint") and shutil.which("node"), "oxlint or node missing")
    def test_an_old_ts_handler_stays_quiet_when_the_change_is_elsewhere(self) -> None:
        old = text("/** Old. */", "export function old(a: () => void): void {", "  try { a(); } catch (e) { a(); }", "}")
        self.assertEqual(self.changed("src/a.ts", old, old + "export const x = 1;\n"), [])
