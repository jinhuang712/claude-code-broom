"""The edit hook: it records an edit for the turn's end, and an edit with nothing more to do costs little."""

from __future__ import annotations

import shutil
import unittest

from support import HEAVY, BroomCase


class EditHookTest(BroomCase):
    def test_an_edit_starts_no_git_and_loads_no_check(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "README.md": "hello\n"})
        for name in ("README.md", "a.py"):
            payload = {"session_id": "idle", "cwd": str(r), "tool_name": "Edit",
                       "tool_input": {"file_path": str(r / name)}}
            git, loaded = self.counted("edit", payload, r)
            self.assertEqual(git, [], name)
            self.assertEqual([m for m in loaded if m in HEAVY], [], name)

    @unittest.skipUnless(shutil.which("oxlint"), "oxlint missing")
    def test_a_file_outside_any_repo_is_a_scratch_draft(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        draft = self.tmp / "scratchpad" / "draft.mjs"  # the kind of draft broom once stopped a turn over
        draft.parent.mkdir()
        draft.write_text("import { readdirSync } from 'node:fs';\n\nexport const x = 1;\n")
        self.hook("edit", {"session_id": "x1", "cwd": str(r), "tool_name": "Write",
                           "tool_input": {"file_path": str(draft)}})
        self.assertEqual(self.hook("stop", {"session_id": "x1", "cwd": str(r), "permission_mode": "default"}), {}, "a draft in a temp directory is no project's code")


if __name__ == "__main__":
    unittest.main()
