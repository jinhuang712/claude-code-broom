"""The check after an edit (editcheck): what a fast linter finds on the lines an edit changed is told to Claude once,
the file is formatted first, and none of it blocks."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from support import BROOM, HAS_PY, HAS_SWIFTLINT, TS_BAD, BroomCase

OLD_FINDING = "import os\n\n\ndef f():\n    return 1\n"  # F401 on line 1, there before any edit
LEAKY = "x = 1\n\n\ndef f():\n    unused = 1\n    return 2\n"  # F841 on line 5


@unittest.skipUnless(HAS_PY, "ruff missing")
class EditCheckTest(BroomCase):
    """The light check after an edit, with ruff, the fast linter every machine here has."""

    def edit(self, r: Path, name: str, text: str, session: str = "s1", **options: str) -> dict:
        (r / name).write_text(text)
        payload = {"session_id": session, "cwd": str(r), "tool_name": "Edit", "tool_input": {"file_path": str(r / name)}}
        return self.hook("edit", payload, cwd=r, **options)

    def told(self, out: dict) -> str:
        """What the hook told Claude: context for the tool call and nothing else, so no block, deny or stop."""
        if not out:
            return ""
        self.assertEqual(list(out), ["hookSpecificOutput"])
        spec = out["hookSpecificOutput"]
        self.assertEqual(sorted(spec), ["additionalContext", "hookEventName"])
        self.assertEqual(spec["hookEventName"], "PostToolUse")
        return spec["additionalContext"]

    def test_a_finding_on_a_line_the_edit_changed_is_told(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        said = self.told(self.edit(r, "a.py", LEAKY))
        self.assertTrue(said.startswith("broom: 1 finding(s) on the lines you changed in a.py: a.py:5 F841 "), said)
        self.assertNotIn("\n", said, "one short line")

    def test_a_finding_on_a_line_the_edit_left_alone_says_nothing(self) -> None:
        r = self.repo({"a.py": OLD_FINDING})
        self.assertEqual(self.edit(r, "a.py", OLD_FINDING + "\n\ndef g():\n    return 2\n"), {})

    def test_a_finding_is_told_once_and_again_after_it_went_away_and_came_back(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.assertIn("F841", self.told(self.edit(r, "a.py", LEAKY)))
        self.assertEqual(self.edit(r, "a.py", LEAKY + "\n\ndef g():\n    return 3\n"), {}, "told once")
        self.assertEqual(self.edit(r, "a.py", "x = 1\n"), {}, "gone")
        self.assertIn("F841", self.told(self.edit(r, "a.py", LEAKY)), "back")
        self.assertIn("F841", self.told(self.edit(r, "a.py", LEAKY, session="s2")), "another session was told nothing")

    def test_a_second_finding_is_told_alone(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.told(self.edit(r, "a.py", LEAKY))
        said = self.told(self.edit(r, "a.py", LEAKY.replace("return 2", "other = 3\n    return 2")))
        self.assertIn("1 finding(s)", said)
        self.assertIn("other", said)
        self.assertNotIn("unused", said)

    def test_a_message_names_a_handful_of_findings_and_counts_the_rest(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        many = "def f():\n" + "".join(f"    v{i} = {i}\n" for i in range(7)) + "    return 1\n"
        said = self.told(self.edit(r, "a.py", many))
        self.assertIn("7 finding(s)", said)
        self.assertEqual(said.count(" F841 "), 5, said)
        self.assertTrue(said.endswith("; and 2 more"), said)

    def test_a_syntax_error_is_told_and_blocks_nothing(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.assertIn("a.py:2", self.told(self.edit(r, "a.py", "x = 1\ndef f(:\n")))

    def test_check_on_off_turns_the_check_off_and_the_other_values_leave_it_on(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.assertEqual(self.edit(r, "a.py", LEAKY, check_on="off"), {})
        self.assertIn("F841", self.told(self.edit(r, "a.py", LEAKY, check_on="commit")))
        self.assertEqual(self.edit(r, "a.py", LEAKY, check_on="off", format_on="off"), {})

    def test_a_file_the_check_leaves_alone_costs_nothing_and_says_nothing(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "notes.md": "hi\n", "gen/g.py": "x = 1\n",
                       ".broom.json": '{"exclude": ["gen/**"]}'})
        self.assertEqual(self.edit(r, "notes.md", "hello\n"), {}, "no language")
        self.assertEqual(self.edit(r, "gen/g.py", LEAKY), {}, "excluded by .broom.json")
        draft = self.tmp / "draft.py"
        draft.write_text(LEAKY)
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Write", "tool_input": {"file_path": str(draft)}}
        self.assertEqual(self.hook("edit", payload, cwd=r), {}, "outside any repo")

    def test_a_file_is_formatted_after_an_edit_unless_format_on_is_commit_or_off(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "ruff.toml": ""})
        messy = "x = {  'a':1 }\n"
        for options, expected in (({"format_on": "commit"}, messy), ({"format_on": "off"}, messy), ({}, 'x = {"a": 1}\n')):
            self.edit(r, "a.py", messy, **options)
            self.assertEqual((r / "a.py").read_text(), expected, options)

    def test_a_missing_linter_says_nothing_and_the_hook_exits_0(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(LEAKY)
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Edit", "tool_input": {"file_path": str(r / "a.py")}}
        p = subprocess.run([str(BROOM), "hook", "edit"], input=json.dumps(payload), capture_output=True, text=True,
                           env=self.fake_path(), cwd=r)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_a_linter_that_fails_says_nothing_and_what_was_told_stands(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.assertIn("F841", self.told(self.edit(r, "a.py", LEAKY)))
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Edit", "tool_input": {"file_path": str(r / "a.py")}}
        env = self.fake_path(fakes={"ruff": "echo 'not json'; echo boom >&2; exit 2"})
        p = subprocess.run([str(BROOM), "hook", "edit"], input=json.dumps(payload), capture_output=True, text=True,
                           env=env, cwd=r)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        self.assertEqual(self.edit(r, "a.py", LEAKY + "\n\ndef g():\n    return 3\n"), {}, "not told again for it")

    def test_a_tool_that_never_finishes_is_cut_off_after_a_moment_and_the_edit_goes_on(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "ruff.toml": ""})
        (r / "a.py").write_text(LEAKY)
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Edit", "tool_input": {"file_path": str(r / "a.py")}}
        env = self.fake_path(keep=("sleep",), fakes={"ruff": "sleep 60"})
        start = time.monotonic()
        p = subprocess.run([str(BROOM), "hook", "edit"], input=json.dumps(payload), capture_output=True, text=True,
                           env=env, cwd=r)
        self.assertLess(time.monotonic() - start, 10, "the formatter and the linter, a moment each")
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    @unittest.skipUnless(shutil.which("oxlint"), "oxlint missing")
    def test_a_ts_file_is_linted_without_the_rules_that_start_a_type_check(self) -> None:
        r = self.ts_repo()
        said = self.told(self.edit(r, "src/main.ts", TS_BAD))
        self.assertIn("src/main.ts:4 eslint(no-unused-vars)", said)
        self.assertNotIn("floating", said, "a rule that needs the type checker")

    @unittest.skipUnless(HAS_SWIFTLINT, "swiftlint missing")
    def test_a_swift_file_is_linted_by_swiftlint(self) -> None:
        r = self.repo({"a.swift": "let x: Any = 1\n"})
        self.assertIn("force_cast", self.told(self.edit(r, "a.swift", "let x: Any = 1\nlet y = x as! String\n")))


if __name__ == "__main__":
    unittest.main()
