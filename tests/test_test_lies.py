"""A test is judged by what it proves (decision 051): in a test file only the 4 test lies keep their level, and every
other smell is a nit."""

from __future__ import annotations

import unittest
from pathlib import Path

from support import HAS_PY, BroomCase, py_function

from broom.config import NIT, TEST_LIES
from broom.smell import Smell

REPO = Path("/r")


def smell(rel: str, metric: str, level: str, *, touched: bool = False) -> Smell:
    return Smell(REPO, REPO / rel, 1, metric, "k", 1, None, "ruff", level, 0, touched=touched)


class LevelRuleTest(unittest.TestCase):
    def test_the_four_test_lies_keep_their_level_in_a_test_file(self) -> None:
        self.assertEqual(sorted(TEST_LIES), ["broad_test_asserts", "skipped_test", "suppression", "swallowed_error"])
        for metric, level in (("skipped_test", "hint"), ("broad_test_asserts", "hint"), ("swallowed_error", "block"),
                              ("suppression", "block"), ("swallowed_error", NIT)):
            self.assertEqual(smell("tests/test_a.py", metric, level).level, level, metric)

    def test_every_other_smell_in_a_test_file_is_a_nit_whatever_its_size_or_age(self) -> None:
        for metric, level in (("function_lines", "block"), ("params", "hint"), ("nesting", "block"),
                              ("duplicate_lines", "hint"), ("type_lines", "hint"), ("type_escape", "hint"),
                              ("globals", "hint"), ("commented_code", "block"), ("unused_params", "hint")):
            self.assertEqual(smell("tests/test_a.py", metric, level).level, NIT, metric)
        self.assertEqual(smell("a.test.ts", "function_lines", "hint", touched=True).level, NIT, "an old smell")

    def test_a_code_file_keeps_every_level(self) -> None:
        self.assertEqual(smell("lib/a.py", "function_lines", "block").level, "block")
        self.assertEqual(smell("lib/a.py", "skipped_test", "hint").level, "hint")

    def test_a_nit_past_the_hard_limit_does_not_stop_anything(self) -> None:
        s = smell("tests/test_a.py", "function_lines", "block")
        self.assertFalse(s.issue().severe)
        self.assertIsNone(s.issue().grown_from)


class R9Case(BroomCase):
    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_r9_a_tests_shape_never_stops_a_commit_only_its_skip_does(self) -> None:
        r = self.repo({"tests/test_a.py": "x = 1\n"})
        many = "def test_many(a, b, c, d, e, f, g, h, i):\n    assert a\n"
        skipped = 'import unittest\n\n\n@unittest.skip("later")\ndef test_later():\n    pass\n'
        (r / "tests/test_a.py").write_text(skipped + "\n\n" + many + "\n\n" + py_function("test_huge", 120))
        self.sh(r, "git", "add", "tests/test_a.py")
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("skipped or disabled test", reason, "the skip stops the commit")
        self.assertIn("nit(s)", reason, "the rest is told")
        self.assertIn("test_huge is 120 code lines long", reason)
        self.assertIn("test_many takes 9 parameters", reason)
        for told in ("test_huge", "test_many"):
            self.assertNotIn("hard limit", reason.split(told)[1].split(")")[0], f"{told} is a nit past the hard limit")
        (r / "tests/test_a.py").write_text(skipped.replace('@unittest.skip("later")\n', "").replace("import unittest\n\n\n", "") + "\n\n" + many
                                           + "\n\n" + py_function("test_huge", 120))
        self.sh(r, "git", "add", "tests/test_a.py")
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "", "without the skip nothing stops")


if __name__ == "__main__":
    unittest.main()
