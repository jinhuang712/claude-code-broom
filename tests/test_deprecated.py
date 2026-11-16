"""`deprecated_api`: a call to something its author marked deprecated is a hint when a change adds it and quiet when it
is old, in each language whose tool broom already runs: ruff in Python, golangci-lint's staticcheck in Go, rustc in
Rust and oxlint with tsgolint in TS/JS. It reads the finding's own words, which name what replaced the API."""

from __future__ import annotations

import json
import os
import shutil
import unittest
from unittest import mock

from support import HAS_GO, HAS_PY, BroomCase

from broom.config import NOTED, SMELL_PRESENCE
from broom.fixes import fixes
from broom.hotspots import smell_counts
from broom.realtree import go_key
from broom.smell import NOTE_CHARS
from broom.smells import find_smells

HAS_CLIPPY = bool(shutil.which("cargo") and shutil.which("cargo-clippy"))
HAS_TYPED_TS = bool(shutil.which("oxlint") and shutil.which("tsgolint"))


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


PY_OLD = text("import unittest", "", "", "class T(unittest.TestCase):", "    def test_a(self):",
              "        self.assertEquals(1, 1)")
PY_ADDED = PY_OLD + text("", "    def test_b(self):", "        self.assertEquals(2, 2)")
GO_MOD = "module example.com/x\n\ngo 1.22\n"
GO_OLD = text("package main", "", 'import "strings"', "", "func Title(s string) string {",
              "\treturn strings.Title(s)", "}")
GO_ADDED = GO_OLD + text("", "func Again(s string) string {", "\treturn strings.Title(s)", "}")
CARGO = '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'
RS_BASE = text('#[deprecated(since = "0.2.0", note = "use `new_fn` instead")]', "pub fn old_fn() -> i32 { 1 }", "",
               "pub fn new_fn() -> i32 { 2 }")
RS_OLD = RS_BASE + text("", "pub fn first() -> i32 {", "    old_fn()", "}")
RS_ADDED = RS_OLD + text("", "pub fn second() -> i32 {", "    old_fn()", "}")
TS_CONFIG = ('{"compilerOptions":{"target":"es2022","module":"nodenext","strict":true,"noEmit":true},'
             '"include":["src"]}\n')
TS_LIB = text("/** Old.", " * @deprecated use newFn instead", " */", "export function oldFn(n: number): number {",
              "  return n;", "}", "", "export function newFn(n: number): number {", "  return n * 2;", "}")
TS_MAIN = text('import { oldFn, newFn } from "./lib.js";', "", "export function first(): number {",
               "  return oldFn(1) + newFn(2);", "}")
TS_ADDED = TS_MAIN + text("", "export function second(): number {", "  return oldFn(3);", "}")
TS_FILES = {"package.json": '{"name":"t","private":true,"type":"module"}\n', "tsconfig.json": TS_CONFIG,
            "src/lib.ts": TS_LIB}


class DeprecatedCase(BroomCase):
    def deprecated(self, files: dict, rel: str, after: str) -> tuple[list[tuple[list[int], str]], list[str]]:
        """The (added lines, text) of each `deprecated_api` smell a change of file `rel` to `after` makes, and the notes."""
        r = self.repo(files)
        (r / rel).write_text(after)
        found, notes = find_smells(r, [r / rel], "HEAD")
        return [(s.added, s.text()) for s in found if s.metric == "deprecated_api"], notes


class TableTest(DeprecatedCase):
    def test_it_is_a_hint_with_a_label_a_fix_and_the_findings_own_words(self) -> None:
        self.assertEqual(SMELL_PRESENCE["deprecated_api"], "hint")
        self.assertIn("deprecated_api", NOTED)
        self.assertIn("deprecated_api", fixes())
        self.assertIn("names it", fixes()["deprecated_api"], "the fix line points at the deprecation note")

    def test_staticcheck_s_words_are_cut_to_the_item_and_its_note(self) -> None:
        said = ("SA1019: strings.Title has been deprecated since Go 1.18 and an alternative has been available since "
                "Go 1.0: Use golang.org/x/text/cases instead. ")
        self.assertEqual(go_key("deprecated_api", said), "strings.Title is deprecated: Use golang.org/x/text/cases instead.")
        self.assertEqual(go_key("deprecated_api", "SA1019: x.Y is deprecated, odd"), "x.Y is deprecated, odd")
        self.assertEqual(go_key("globals", "SA1019: x"), "", "nothing is named for the other smells")

    def test_a_long_note_is_cut_with_dots(self) -> None:
        from broom.smell import Smell
        from pathlib import Path

        s = Smell(Path("/r"), Path("/r/a.py"), 3, "deprecated_api", "w" * (NOTE_CHARS + 20), 1, None, "ruff", "hint", 0, [3])
        self.assertTrue(s.text().endswith("w" * NOTE_CHARS + "...)"), s.text())


@unittest.skipUnless(HAS_PY, "ruff missing")
class PythonTest(DeprecatedCase):
    def test_a_deprecated_call_a_change_adds_is_found_with_what_replaced_it(self) -> None:
        found, _ = self.deprecated({"t.py": PY_OLD}, "t.py", PY_ADDED)
        self.assertEqual([lines for lines, _ in found], [[9]])
        self.assertIn("`assertEquals` is deprecated, use `assertEqual`", found[0][1])
        self.assertIn("1 more call(s) to a deprecated API (2 in the file, was 1)", found[0][1])

    def test_an_old_one_stays_quiet_and_so_does_a_change_elsewhere(self) -> None:
        found, _ = self.deprecated({"t.py": PY_OLD}, "t.py", PY_OLD.replace("(1, 1)", "(1, 1)  # same"))
        self.assertEqual(found, [], "an edited line that keeps its occurrence adds nothing")
        found, _ = self.deprecated({"t.py": PY_OLD}, "t.py", "VALUE = 1\n\n\n" + PY_OLD)
        self.assertEqual(found, [], "a call that only moved down is old")

    def test_a_deprecated_import_counts_and_a_test_file_is_not_exempt(self) -> None:
        files = {"tests/test_a.py": "X = 1\n"}
        found, _ = self.deprecated(files, "tests/test_a.py", "from collections import Mapping\n\nX = 1\n")
        self.assertEqual([lines for lines, _ in found], [[1]])
        self.assertIn("Import from `collections.abc` instead: `Mapping`", found[0][1])

    def test_typings_old_aliases_are_not_counted_for_every_codebase_older_than_them_holds_them(self) -> None:
        aliases = text("from typing import (", "    Callable,", "    Dict,", ")", "from typing import ContextManager, List",
                       "", "X = 1")
        found, _ = self.deprecated({"a.py": "X = 1\n"}, "a.py", aliases)
        self.assertEqual(found, [])

    def test_smells_off_turns_it_off(self) -> None:
        r = self.repo({"t.py": PY_OLD, ".broom.json": json.dumps({"smells_off": ["deprecated_api"]})})
        (r / "t.py").write_text(PY_ADDED)
        found, _ = find_smells(r, [r / "t.py"], "HEAD")
        self.assertEqual([s.metric for s in found if s.metric == "deprecated_api"], [])


@unittest.skipUnless(HAS_GO, "go or golangci-lint missing")
class GoTest(DeprecatedCase):
    FILES = {"go.mod": GO_MOD, "main.go": GO_OLD}

    def test_a_deprecated_call_a_change_adds_is_found_with_the_note_of_staticcheck(self) -> None:
        found, _ = self.deprecated(self.FILES, "main.go", GO_ADDED)
        self.assertEqual([lines for lines, _ in found], [[10]], "line 6, the old call, is not in it")
        self.assertIn("strings.Title is deprecated:", found[0][1])
        self.assertIn("Use golang.org/x/text/cases instead.", found[0][1])

    def test_an_old_one_stays_quiet_and_only_that_check_of_staticcheck_counts(self) -> None:
        found, _ = self.deprecated(self.FILES, "main.go", GO_OLD + "\n// a note\n")
        self.assertEqual(found, [])
        shouting = GO_OLD + text("", "func Bad() error {", '\treturn errors.New("Bad thing.")', "}")
        found, _ = self.deprecated({"go.mod": GO_MOD, "main.go": GO_OLD}, "main.go",
                                   shouting.replace('import "strings"', 'import (\n\t"errors"\n\t"strings"\n)'))
        self.assertEqual(found, [], "ST1005 and the rest of staticcheck's checks are not asked for")


@unittest.skipUnless(HAS_CLIPPY, "cargo or clippy missing")
class RustTest(DeprecatedCase):
    FILES = {"Cargo.toml": CARGO, "src/lib.rs": RS_OLD}

    def test_a_deprecated_call_a_change_adds_is_found_with_the_note_of_the_attribute(self) -> None:
        found, _ = self.deprecated(self.FILES, "src/lib.rs", RS_ADDED)
        self.assertEqual([lines for lines, _ in found], [[11]], "line 7, the old call, is not in it")
        self.assertIn("use of deprecated function `old_fn`: use `new_fn` instead", found[0][1])

    def test_an_old_one_stays_quiet(self) -> None:
        found, _ = self.deprecated(self.FILES, "src/lib.rs", RS_OLD + "\n// a note\n")
        self.assertEqual(found, [])


@unittest.skipUnless(HAS_TYPED_TS, "oxlint or tsgolint missing")
class TypeScriptTest(DeprecatedCase):
    FILES = {**TS_FILES, "src/main.ts": TS_MAIN}

    def test_a_deprecated_call_a_change_adds_is_found_with_the_jsdoc_note(self) -> None:
        found, notes = self.deprecated(self.FILES, "src/main.ts", TS_ADDED)
        self.assertEqual([lines for lines, _ in found], [[8]], "line 4, the old call, is not in it")
        self.assertIn("`oldFn` is deprecated. use newFn instead", found[0][1])
        self.assertEqual([n for n in notes if "tsgolint" in n], [])

    def test_an_old_one_stays_quiet(self) -> None:
        found, _ = self.deprecated(self.FILES, "src/main.ts", TS_MAIN + "\n// a note\n")
        self.assertEqual(found, [])

    def test_without_tsgolint_nothing_is_found_and_one_note_says_so_and_the_cycles_still_run(self) -> None:
        env = self.fake_path(keep=("oxlint", "node"))
        with mock.patch.dict(os.environ, {"PATH": env["PATH"]}):
            found, notes = self.deprecated(self.FILES, "src/main.ts", TS_ADDED)
        self.assertEqual(found, [])
        self.assertEqual([n for n in notes if "tsgolint" in n],
                         ["oxlint-tsgolint is missing, so deprecated TS/JS APIs aren't measured "
                          "(npm i -g oxlint-tsgolint)"])
        self.assertEqual([n for n in notes if "failed" in n or "timeout" in n], [], "oxlint ran without --type-aware")


class CounterTest(DeprecatedCase):
    def test_the_check_up_counts_them_and_leaves_the_count_out_when_a_tool_behind_it_is_short(self) -> None:
        r = self.repo({"README.md": "x\n"})
        for note in ("missing:ruff (brew install ruff)", "timeout:cargo clippy measuring smells in /r (cold build?)",
                     "oxlint-tsgolint is missing, so deprecated TS/JS APIs aren't measured (npm i -g oxlint-tsgolint)",
                     "timeout:the time of this scan ran out before golangci-lint measured smells"):
            with self.subTest(note):
                self.assertIsNone(smell_counts(r, [], [note])["deprecated_api"])
        self.assertEqual(smell_counts(r, [], [])["deprecated_api"], {})


@unittest.skipUnless(HAS_PY, "ruff missing")
class CheckupTest(DeprecatedCase):
    def test_a_counter_that_grew_is_told_and_the_diagnosis_lists_it(self) -> None:
        r = self.repo({"t.py": PY_OLD})
        env = {**self.env, "PATH": self.fake_path(keep=("ruff",))["PATH"]}
        self.assertEqual(self.session(r, "s1", env, "session-scan"), {}, "the first numbers are silent")
        (r / "t.py").write_text(PY_ADDED)
        self.sh(r, "git", "commit", "-qam", "more")
        told = self.session(r, "s2", env, "session-scan")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("calls to deprecated APIs 1 -> 2 (t.py)", told)
        rows = {c["counter"]: c for c in json.loads(self.cli(r, "diagnose", "--json", env=env).stdout)["checkup"]["counters"]}
        self.assertEqual((rows["deprecated_api"]["now"], rows["deprecated_api"]["label"]),
                         (2, "calls to deprecated APIs"))
