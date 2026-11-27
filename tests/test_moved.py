"""A known issue whose file names a linked worktree that is gone names the main checkout's file once a tail of its
path proves it, and one that no line proves stays marked."""

from __future__ import annotations

import json

from support import BroomCase, py_function

from broom.gate import key_of


class MovedTest(BroomCase):
    def test_an_entry_of_a_deleted_worktree_names_the_main_checkouts_file_once_proven(self) -> None:
        text = py_function("huge", 120)
        r = self.repo({"a.py": text})
        gone = r / "wt-side" / "a.py"  # a worktree inside the repo, deleted since
        msg, line = "huge is 120 code lines long (over 50)", text.splitlines()[0].strip()
        old = {"file": str(gone), "line": 1, "tool": "smells", "rule": "function_lines", "msg": msg, "t": 1}
        lost = {**old, "msg": "kept is 120 code lines long (over 50)"}
        data = {key_of(gone, "smells", "function_lines", msg, line): old,  # keyed on the worktree's path, as before 0.28.1
                key_of(gone, "smells", "function_lines", lost["msg"], "def kept(x):"): lost}  # no line here proves it
        (self.tmp / "data").mkdir(exist_ok=True)
        (self.tmp / "data" / "baseline.json").write_text(json.dumps(data))
        out = self.cli(r, "known").stdout
        self.assertIn("2 known issue(s), 1 of them with their code changed", out)
        self.assertIn(f"{r / 'a.py'}:1  smells function_lines  {msg}", out)
        self.assertIn(f"wt-side/a.py:1  smells function_lines  {lost['msg']}", out)
        stored = json.loads((self.tmp / "data" / "baseline.json").read_text())
        self.assertIn(key_of(r / "a.py", "smells", "function_lines", msg, line), stored, "the key the main checkout gives")
        (r / "a.py").write_text(text + "\n")
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "", "so it is known there")
