"""A repeated block is counted in code lines (decision 039), as every length is."""

from __future__ import annotations

import shutil
import unittest

from support import BroomCase

from broom.smells import find_smells


class CloneLinesTest(BroomCase):
    @unittest.skipUnless(shutil.which("jscpd"), "jscpd missing")
    def test_a_copy_counts_the_code_lines_of_its_span_not_its_comments_and_blanks(self) -> None:
        notes = "".join(f"    # note {i} on the thing\n\n" for i in range(25))  # 50 lines, no code
        body = "".join(f"    x += {i}\n" for i in range(4))
        r = self.repo({"a.py": f"def one(x):\n{notes}{body}    return x\n"})
        (r / "b.py").write_text(f"def two(x):\n{notes}{body}    return x\n")
        found, _ = find_smells(r, [r / "b.py"], "HEAD")
        self.assertEqual([s for s in found if s.metric == "duplicate_lines"], [], "6 code lines in 56 lines")
        longer = "".join(f"    x += {i}\n" for i in range(12))
        (r / "c.py").write_text(f"def three(x):\n{notes}{longer}    return x\n")
        (r / "d.py").write_text(f"def four(x):\n{notes}{longer}    return x\n")
        found, _ = find_smells(r, [r / "d.py"], "HEAD")
        self.assertEqual([(s.level, s.value) for s in found if s.metric == "duplicate_lines"], [("hint", 14)],
                         "14 code lines in 64 lines")


if __name__ == "__main__":
    unittest.main()
