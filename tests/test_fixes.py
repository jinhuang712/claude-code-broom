"""The fix lines: one home for the usual fix of each smell, `broom fixes`, and where the blocks and hints carry them."""

from __future__ import annotations

import json
from pathlib import Path

from support import BroomCase, py_function

from broom.config import DEAD_CODE, SMELL_LIMITS, SMELL_PRESENCE, TESTS_FAILED, TESTS_NOT_RUN
from broom.findings import Issue
from broom.fixes import NOT_A_FIX, fixes, how_to_fix
from broom.gate import MAX_CHARS, render
from broom.smells import Smell, nits_text

WAY_OUT = ('Accept only for a real reason, such as a false positive or a refactor that comes in a later step: run '
           '`broom known --accept "<why>"`, then commit again.')


def smell_issue(rule: str, n: int = 1, tool: str = "smells") -> Issue:
    return Issue(tool, Path("/r"), Path(f"/r/a{n}.py"), n, 0, rule, f"{rule} finding {n}")


class FixLinesTest(BroomCase):
    def test_every_smell_has_a_fix_line_under_160_characters(self) -> None:
        names = {*SMELL_LIMITS, *SMELL_PRESENCE, DEAD_CODE, TESTS_NOT_RUN, TESTS_FAILED}  # the last two: no test ran
        self.assertEqual(sorted(names - set(fixes())), [], "a smell without a fix line")
        self.assertEqual(sorted(set(fixes()) - names), [], "a fix line for no smell")
        for name, line in fixes().items():
            self.assertTrue(0 < len(line) < 160, name)
            self.assertTrue(line.endswith("."), name)

    def test_fixes_prints_all_the_named_ones_or_json(self) -> None:
        out = self.cli(self.tmp, "fixes")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(len(out.stdout.splitlines()), len(fixes()))
        self.assertIn("function_lines: Extract the steps the function takes", out.stdout)
        named = self.cli(self.tmp, "fixes", "todo", "nesting").stdout.splitlines()
        self.assertEqual([x.split(":")[0] for x in named], ["todo", "nesting"], "in the order asked")
        self.assertEqual(json.loads(self.cli(self.tmp, "fixes", "--json", "todo").stdout),
                         {"todo": fixes()["todo"]})
        self.assertEqual(json.loads(self.cli(self.tmp, "fixes", "--json").stdout), fixes())

    def test_an_unknown_name_exits_1_with_the_names(self) -> None:
        out = self.cli(self.tmp, "fixes", "todo", "nope")
        self.assertEqual((out.returncode, out.stdout), (1, ""))
        self.assertIn("unknown smell nope", out.stderr)
        self.assertIn("function_lines, ", out.stderr)

    def test_how_to_fix_names_each_kind_once_in_order_and_leaves_lint_out(self) -> None:
        kinds = ["complexity", "function_lines", "complexity", "F401"]
        self.assertEqual(how_to_fix(kinds), ["How to fix:", f"  complexity: {fixes()['complexity']}",
                                             f"  function_lines: {fixes()['function_lines']}", NOT_A_FIX])
        self.assertEqual(how_to_fix(["F401"]), [])


class BlockMessageTest(BroomCase):
    def test_a_block_lists_findings_then_how_to_fix_then_the_way_out_then_what_was_skipped(self) -> None:
        issues = [smell_issue("function_lines"), smell_issue("todo", 2), smell_issue("function_lines", 3),
                  smell_issue("F401", 4, tool="ruff")]
        text = render("[broom] Commit blocked: 4 issue(s) in the files being committed. Fix them and commit again.",
                      issues, ["missing:ruff (brew install ruff)"], set(), WAY_OUT)
        rows = text.splitlines()
        self.assertEqual(rows[0][:30], "[broom] Commit blocked: 4 issu")
        self.assertNotIn("known --accept", rows[0], "the way out is no longer in the first line")
        found, fix, tail = (text.index(s) for s in ("a1.py:1", "How to fix:", WAY_OUT))
        self.assertLess(found, fix)
        self.assertLess(fix, tail)
        self.assertLess(tail, text.index("Skipped:"))
        self.assertIn(f"  function_lines: {fixes()['function_lines']}\n  todo: {fixes()['todo']}\n{NOT_A_FIX}", text)
        self.assertEqual(text.count("  function_lines: "), 1, "one line per kind")
        self.assertNotIn("F401:", text, "a linter's own message says it")
        self.assertEqual(rows[rows.index(WAY_OUT) - 1], "", "the way out stands apart")

    def test_lint_findings_alone_get_no_fix_lines_and_no_not_a_fix(self) -> None:
        text = render("[broom] 1 issue(s).", [smell_issue("F401", tool="ruff")], [], set(), WAY_OUT)
        self.assertNotIn("How to fix", text)
        self.assertNotIn("Not a fix", text)
        self.assertTrue(text.endswith(WAY_OUT))

    def test_without_a_way_out_the_report_is_as_it_was(self) -> None:
        text = render("[broom] 1 code smell(s).", [smell_issue("todo")], [], set())
        self.assertNotIn("How to fix", text, "a sweep isn't a block")
        self.assertTrue(text.endswith("a1.py:1:0  todo  todo finding 1"))

    def test_a_long_message_shows_fewer_findings_and_says_how_many_more(self) -> None:
        issues = [Issue("smells", Path("/r"), Path(f"/r/f{n}.py"), n, 0, "todo", "x" * 400) for n in range(1, 41)]
        text = render("[broom] 40 issue(s).", issues, ["timeout:ruff took too long"], set(), WAY_OUT)
        self.assertLess(len(text), MAX_CHARS)
        self.assertGreater(len(text), MAX_CHARS - 1000, "as many findings as fit")
        shown = text.count("  f")
        self.assertLess(shown, 40)
        self.assertIn(f"... and {40 - shown} more", text)
        self.assertIn("How to fix:", text)
        self.assertTrue(text.index(WAY_OUT) < text.index("Skipped:"), "the tail is never what gives way")

    def test_one_finding_always_shows(self) -> None:
        text = render("h", [smell_issue("todo")], [], set(), "w" * (MAX_CHARS + 1))
        self.assertIn("a1.py:1:0", text)


class RealBlockTest(BroomCase):
    def huge(self) -> Path:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        return r

    def test_a_commit_block_has_the_shape(self) -> None:
        r = self.huge()
        self.sh(r, "git", "add", "a.py")
        text = self.denied(self.commit(r, "git commit -m x"))
        self.assertEqual(text.splitlines()[0], "[broom] Commit blocked: 1 issue(s) in the files being committed. "
                                               "Fix them and commit again.")
        self.assertIn("huge is 120 lines long (hard limit 100; new)", text)
        self.assertIn(f"How to fix:\n  function_lines: {fixes()['function_lines']}\n{NOT_A_FIX}\n", text)
        self.assertTrue(text.index("How to fix:") < text.index(WAY_OUT))

    def test_a_turn_end_block_has_the_shape(self) -> None:
        r = self.huge()
        self.hook("edit", {"session_id": "s1", "cwd": str(r), "tool_name": "Edit",
                           "tool_input": {"file_path": str(r / "a.py")}})
        text = self.hook("stop", {"session_id": "s1", "cwd": str(r), "permission_mode": "default"})["reason"]
        self.assertRegex(text.splitlines()[0], r"^\[broom\] \d+ issue\(s\) in this turn's changes\. "
                                               r"Fix them before finishing\.$")
        self.assertIn("function_lines: ", text)
        self.assertIn('then stop again.', text)
        self.assertTrue(text.endswith('Block 1 of 3. After 3 blocks the turn ends, and the user is told what is '
                                      'still open.'))
        self.assertIn("Trying again passes nothing", text)

    def test_with_accepting_off_the_way_out_says_there_is_none(self) -> None:
        r = self.huge()
        self.sh(r, "git", "add", "a.py")
        self.env["BROOM_NO_ACCEPT"] = "1"
        text = self.denied(self.commit(r, "git commit -m x"))
        self.assertTrue(text.splitlines()[0].endswith("Fix them and commit again."))
        self.assertIn("Fixing is the only way out: accepting them is off here (BROOM_NO_ACCEPT).", text)
        self.assertNotIn("broom known --accept", text)


class NoteTextTest(BroomCase):
    def note(self, metric: str, n: int) -> Smell:
        return Smell(self.tmp, self.tmp / f"a{n}.py", n, metric, metric, 3, None, "t", "note", 0, [n])

    def test_a_note_ends_with_the_fix_lines_of_its_first_three_kinds(self) -> None:
        kinds = ["todo", "debug_output", "todo", "globals", "magic_numbers"]
        text = nits_text([self.note(k, n) for n, k in enumerate(kinds, 1)])
        rows = text.splitlines()
        self.assertTrue(rows[0].startswith("broom: 5 nit(s) this change made worse; nothing stops on "
                                           "them: "))
        self.assertEqual(rows[1:], ["How to fix:", *[f"  {k}: {fixes()[k]}" for k in ("todo", "debug_output", "globals")]])
