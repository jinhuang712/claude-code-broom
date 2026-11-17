"""The hooks at a turn's two ends: a turn that changed no code ends with one git call and no check loaded."""

from __future__ import annotations

import unittest

from support import HEAVY, BroomCase


class TurnHooksTest(BroomCase):
    def test_a_turn_that_changed_no_code_ends_with_one_git_call_and_no_check_loaded(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "README.md": "hello\n"})
        base = {"session_id": "idle", "cwd": str(r)}
        self.hook("prompt", base)
        (r / "README.md").write_text("hello again\n")
        git, loaded = self.counted("stop", base, r)
        self.assertEqual(len(git), 1, git)
        self.assertEqual([m for m in loaded if m in HEAVY], [])
        again, _ = self.counted("stop", base, r)
        self.assertEqual(len(again), 1, "and so does the next one")

    def test_a_turn_that_changed_code_is_still_checked(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        base = {"session_id": "busy", "cwd": str(r)}
        self.hook("prompt", base)
        (r / "a.py").write_text("import os\nx = 1\n")
        _, loaded = self.counted("stop", base, r)
        self.assertIn("broom.commitgate", loaded, "the check is loaded when there is code to check")


if __name__ == "__main__":
    unittest.main()
