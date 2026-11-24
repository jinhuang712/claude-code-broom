"""A change against its base (change.py): the lines it changed, those it only moved and those that are code lines."""

from __future__ import annotations

import unittest

from support import BroomCase

from broom.change import Change

BEFORE = "import a\nimport b\nx = 1\ny = 2\n"


class ChangeTest(BroomCase):
    def test_of_the_changed_lines_only_the_code_lines_touch_anything(self) -> None:
        now = BEFORE.replace("y = 2\n", "# why y is 3\n\ny = 3\n")
        r = self.repo({"a.py": BEFORE})
        (r / "a.py").write_text(now)
        change = Change(r, "HEAD", {"a.py": now}, {"a.py": BEFORE})
        self.assertEqual(change.lines("a.py"), {4, 5, 6})
        self.assertEqual(change.code_lines("a.py"), {6}, "the comment and the blank line it added are no code lines")

    def test_a_line_whose_text_the_base_held_is_only_moved(self) -> None:
        now = "import b\nx = 1\ny = 2\nimport a\nz = 3\n"
        r = self.repo({"a.py": BEFORE})
        (r / "a.py").write_text(now)
        change = Change(r, "HEAD", {"a.py": now}, {"a.py": BEFORE})
        self.assertEqual((change.only_moved("a.py", 4), change.only_moved("a.py", 5)), (True, False))

    def test_without_a_base_every_line_counts(self) -> None:
        r = self.repo({"a.py": BEFORE})
        change = Change(r, None, {"a.py": BEFORE})
        self.assertEqual((change.lines("a.py"), change.code_lines("a.py")), (None, None))
        self.assertFalse(change.only_moved("a.py", 1))


if __name__ == "__main__":
    unittest.main()
