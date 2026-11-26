"""Old smells in touched code: a change is told the old sized smells of the functions and files it touches, never
those of what it leaves alone; and one already past the hard limit may not grow on a reason alone."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from support import HAS_PY, HAS_SWIFTLINT, BroomCase, no_depcruise, py_function

from broom.findings import Issue
from broom.gate import issue_key, line_text
from broom.smells import find_smells
from broom.state import short_hash

QUIET = {"smells_off": ["dead_code"]}  # a function nothing calls is dead code too: not what these tests are about
TOUCHED = "you touched it, clean it up in this change"


def ts_function(name: str, lines: int) -> str:
    body = "".join(f"  x += {i};\n" for i in range(lines - 3))
    return f"export function {name}(x: number): number {{\n{body}  return x;\n}}\n"


class TouchedCase(BroomCase):
    def repo(self, files: dict, config: dict = None) -> Path:
        return super().repo({".broom.json": json.dumps({**QUIET, **(config or {})}), **files})

    def touched(self, repo: Path, *names: str) -> list:
        """The texts of the touched hints found in `names` against HEAD."""
        found, _ = find_smells(repo, [repo / n for n in names], "HEAD")
        return [s.text() for s in found if s.touched]

    def edit(self, repo: Path, name: str) -> None:
        self.hook("edit", {"session_id": "s1", "cwd": str(repo), "tool_name": "Edit",
                           "tool_input": {"file_path": str(repo / name)}})

    def stop(self, repo: Path) -> dict:
        return self.hook("stop", {"session_id": "s1", "cwd": str(repo), "permission_mode": "default"})


class AcceptedInAWorktreeTest(TouchedCase):
    def test_what_was_accepted_in_a_linked_worktree_stays_known_in_the_main_checkout(self) -> None:
        text = py_function("legacy", 60)
        r = self.repo({"a.py": text})
        linked = self.tmp / "linked"
        self.sh(r, "git", "worktree", "add", "-q", str(linked), "-b", "side")
        for tree in (linked, r):  # the same change in both, as when the worktree's work lands on the main checkout
            (tree / "a.py").write_text(text.replace("x += 3\n", "x += 333\n"))
            self.sh(tree, "git", "add", "a.py")
        self.assertIn(TOUCHED, self.denied(self.commit(linked, "git commit -m touch")))
        self.assertIn("accepted 1 issue(s)", self.cli(linked, "known", "--accept", "its refactor comes next").stdout)
        self.assertEqual(self.denied(self.commit(linked, "git commit -m touch")), "")
        self.assertEqual(self.denied(self.commit(r, "git commit -m touch")), "", "known there, so known here")
        listed = [self.cli(tree, "known").stdout for tree in (linked, r)]
        self.assertIn(f"{r / 'a.py'}:1  smells function_lines", listed[1], "listed where the work lands")
        self.assertEqual(listed[0], listed[1], "and the worktree lists the same")

    def test_a_finding_of_the_main_checkout_keeps_the_key_it_had(self) -> None:
        r = self.repo({"a.py": py_function("legacy", 60)})
        issue = Issue("smells", r, r / "a.py", 1, 0, "function_lines", "legacy is 60 code lines long (over 50)")
        old = short_hash(f"{issue.file}|{issue.tool}|{issue.rule}|{issue.msg}|{line_text(issue.file, issue.line)}")
        self.assertEqual(issue_key(issue), old, "so what was accepted before this version stays known")


class TouchedHintTest(TouchedCase):
    def test_a_touched_old_function_hints_and_one_beside_it_that_isnt_touched_doesnt(self) -> None:
        text = py_function("touched_one", 60) + "\n\n" + py_function("left_alone", 70).replace("+=", "-=")
        r = self.repo({"a.py": text})
        (r / "a.py").write_text(text.replace("x += 3\n", "x += 333\n"))
        found, _ = find_smells(r, [r / "a.py"], "HEAD")
        self.assertEqual([(s.line, s.level, s.text()) for s in found if s.metric == "function_lines"],
                         [(1, "hint", f"touched_one is 60 code lines long (over 50; was 60: {TOUCHED})")])
        off = self.repo({"a.py": text}, {"smells_off": ["function_lines"]})  # the config is read once per repo
        (off / "a.py").write_text(text.replace("x += 3\n", "x += 333\n"))
        self.assertEqual(self.touched(off, "a.py"), [], "smells_off turns it off as before")

    def test_a_function_that_shrank_but_is_still_long_hints_too_and_one_that_grew_is_the_old_finding(self) -> None:
        r = self.repo({"a.py": py_function("legacy", 150)})
        (r / "a.py").write_text(py_function("legacy", 140))
        self.assertEqual(self.touched(r, "a.py"), [f"legacy is 140 code lines long (over 50; was 150: {TOUCHED})"])
        (r / "a.py").write_text(py_function("legacy", 155))
        found, _ = find_smells(r, [r / "a.py"], "HEAD")
        self.assertEqual([(s.level, s.touched) for s in found], [("block", False)], "worse is a block, not a hint")

    def test_a_file_that_gained_a_code_line_hints_and_one_whose_imports_only_changed_doesnt(self) -> None:
        code = "".join(f"x{i} = {i}\n" for i in range(25))
        r = self.repo({"a.py": code}, {"limits": {"file_lines": [10, 40]}})
        (r / "a.py").write_text("import os\nfrom pathlib import (\n    Path,\n)\n" + code)
        self.assertEqual(self.touched(r, "a.py"), [], "only imports grew")
        (r / "a.py").write_text(code + "y = 1\n")
        self.assertEqual(self.touched(r, "a.py"), [f"the file is 26 code lines long (over 10; was 25: {TOUCHED})"])

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_in_python_parameters_nesting_complexity_and_ternaries_hint_when_their_function_is_touched(self) -> None:
        many = 'def many(a, b, c, d, e, f):\n    _ = "mark_many"\n    return a + b + c + d + e + f\n'
        deep = ('def deep(x):\n    _ = "mark_deep"\n    if x:\n        if x > 1:\n            if x > 2:\n'
                '                if x > 3:\n                    if x > 4:\n                        return x\n    return 0\n')
        branchy = ('def branchy(x):\n    _ = "mark_branchy"\n'
                   + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(11)) + "    return -1\n")
        twisty = 'def twisty(x):\n    _ = "mark_twisty"\n    return 1 if x else 2 if x > 1 else 3\n'
        calm = 'def calm():\n    _ = "mark_calm"\n    return 1\n'
        text = "\n\n".join([many, deep, branchy, twisty, calm])
        r = self.repo({"a.py": text})
        said = {"many": "many takes 6 parameters (over 5; was 6", "deep": "blocks nest 5 levels deep (over 4; was 5",
                "branchy": "branchy has complexity 12 (over 10; was 12",
                "twisty": "a ternary nests inside another (over 0; was 1", "calm": None}
        for name, start in said.items():
            with self.subTest(name):
                (r / "a.py").write_text(text.replace(f'"mark_{name}"', f'"edited_{name}"'))
                found = self.touched(r, "a.py")
                if start is None:
                    self.assertEqual(found, [], "a function beside the old smells, touched alone")
                else:
                    self.assertEqual(len(found), 1, found)
                    self.assertTrue(found[0].startswith(start) and found[0].endswith(f": {TOUCHED})"), found)

    @unittest.skipUnless(shutil.which("oxlint"), "oxlint missing")
    def test_in_ts_only_lengths_tell_a_touch_and_the_rest_stays_as_it_was(self) -> None:
        many = "export function many(a: number, b: number, c: number, d: number, e: number, f: number) {\n  return a;\n}\n"
        text = many + "\n" + ts_function("longer", 60)
        r = self.repo({"a.ts": text})
        (r / "a.ts").write_text(text.replace("return a;", "return b;").replace("x += 3;", "x += 33;"))
        with no_depcruise():
            found, notes = find_smells(r, [r / "a.ts"], "HEAD")
        self.assertEqual(notes, [])
        self.assertEqual([s.text() for s in found if s.touched],
                         [f"longer is 60 code lines long (over 50; was 60: {TOUCHED})"], "no parameter hint, though touched")

    @unittest.skipUnless(HAS_SWIFTLINT and shutil.which("swiftc"), "swiftlint or swiftc missing")
    def test_in_swift_a_change_near_the_end_of_a_function_with_comments_in_it_touches_it(self) -> None:
        body = "".join(f"    x += {i}\n    // note {i}\n" for i in range(55))  # 55 code lines in 110 lines
        text = f"func commented(_ x: Int) -> Int {{\n    var x = x\n{body}    return x\n}}\n"
        r = self.repo({"a.swift": text})
        (r / "a.swift").write_text(text.replace("x += 54", "x += 99"))  # past line + length, inside the function
        found, _ = find_smells(r, [r / "a.swift"], "HEAD")
        self.assertEqual([(s.key, s.touched, s.span) for s in found if s.metric == "function_lines"],
                         [("commented", True, 114)])


class AcceptTest(TouchedCase):
    def block_line(self, reason: str, name: str) -> str:
        return next(row for row in reason.splitlines() if f"{name} is " in row)

    def test_a_function_past_the_hard_limit_that_grew_cant_be_accepted_and_one_that_crossed_it_can(self) -> None:
        r = self.repo({"a.py": py_function("legacy", 150), "b.py": "x = 1\n",
                       "c.py": py_function("crossing", 90).replace("+=", "*=")})
        (r / "a.py").write_text(py_function("legacy", 155))
        (r / "b.py").write_text(py_function("fresh", 120).replace("+=", "-="))
        (r / "c.py").write_text(py_function("crossing", 120).replace("+=", "*="))
        self.sh(r, "git", "add", "-A")
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertTrue(self.block_line(reason, "legacy").endswith(
            "legacy is 155 code lines long (hard limit 100; was 150)  [can't be accepted: was 150, already past the hard limit]"))
        self.assertNotIn("can't be accepted", self.block_line(reason, "fresh"))
        self.assertNotIn("can't be accepted", self.block_line(reason, "crossing"), "it was 90, under the hard limit")
        self.assertIn("broom known --accept", reason, "the way out stays for the others")
        out = self.cli(r, "known", "--accept", "meant to")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("broom: 1 can't be accepted: it was already past the hard limit and grew; bring it back to 150 "
                      "or fewer, or extract what you added", out.stdout)
        self.assertIn("accepted 2 issue(s) as known (meant to)", out.stdout)
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("legacy is 155", reason)
        self.assertNotIn("fresh is", reason)
        again = self.cli(r, "known", "--accept", "please")
        self.assertEqual((again.returncode, again.stdout), (1, ""))
        self.assertIn("1 can't be accepted", again.stderr)
        (r / "a.py").write_text(py_function("legacy", 140))  # back under its old size: a touched old smell, a hint
        self.sh(r, "git", "add", "a.py")
        self.assertIn(f"legacy is 140 code lines long (over 50; was 150: {TOUCHED})",
                      self.denied(self.commit(r, "git commit -m x")), "a hint stops the commit too")

    def test_giving_up_ends_the_turn_with_the_grown_smell_open_and_the_next_commit_stops_on_it(self) -> None:
        r = self.repo({"a.py": py_function("legacy", 150)})
        (r / "a.py").write_text(py_function("legacy", 155))
        self.edit(r, "a.py")
        reason = self.stop(r)["reason"]
        self.assertIn("[can't be accepted: was 150, already past the hard limit]", reason)
        out = self.cli(r, "known", "--accept", "just this once")
        self.assertEqual(out.returncode, 1)
        self.assertIn("1 can't be accepted", out.stderr)
        for _ in range(2):
            self.assertEqual(self.stop(r).get("decision"), "block", "stopping again passes nothing")
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom GAVE UP after 3 blocks: 1 finding(s) left unfixed and unaccepted: a.py:1 "
                         "function_lines; broom let 1 through this turn: 1 function_lines (gave-up)")
        self.assertEqual(self.cli(r, "known").stdout.strip(), "broom: no known issues here")
        self.sh(r, "git", "add", "a.py")
        self.assertIn("legacy is 155", self.denied(self.commit(r, "git commit -m x")))


class HintFlowTest(TouchedCase):
    def test_a_touched_hint_stops_a_commit_and_a_turn_and_passes_with_a_reason(self) -> None:
        r = self.repo({"a.py": py_function("middling", 70)})
        (r / "a.py").write_text(py_function("middling", 70).replace("x += 3\n", "x += 333\n"))
        self.sh(r, "git", "add", "a.py")
        denial = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn(f"a.py:1:0  function_lines  middling is 70 code lines long (over 50; was 70: {TOUCHED})", denial)
        self.assertIn("  function_lines: Extract", denial, "its usual fix line, like any block")
        self.edit(r, "a.py")
        reason = self.stop(r)["reason"]
        self.assertIn(f"middling is 70 code lines long (over 50; was 70: {TOUCHED})", reason)
        self.assertNotIn("can't be accepted", reason)
        self.assertEqual(self.cli(r, "known", "--accept", "old and fine").returncode, 0)
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom let 1 through this turn: 1 function_lines (accepted: old and fine)")
        self.assertEqual(self.commit(r, "git commit -m x"), {}, "known now")


class UntouchedTest(TouchedCase):
    def test_a_change_gets_no_hint_and_no_block_for_an_old_smell_in_a_function_or_a_file_it_didnt_touch(self) -> None:
        """Goal R3."""
        old = (py_function("legacy", 150) + "\n\n" + py_function("middling", 70).replace("+=", "-=")
               + "\n\ndef small():\n    return 1\n")
        r = self.repo({"a.py": old}, {"limits": {"file_lines": [100, 1000]}})  # the file is past its soft limit too
        (r / "a.py").write_text(old.replace("return 1", "return 2"))
        found, _ = find_smells(r, [r / "a.py"], "HEAD")
        self.assertEqual([s.text() for s in found if s.metric in ("function_lines", "file_lines")], [])
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.edit(r, "a.py")
        self.assertEqual(self.stop(r), {})
