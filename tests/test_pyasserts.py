"""What makes a Python test assert, read from its tree: a same-file helper that asserts, and no function that returns
a value."""

from __future__ import annotations

import ast
import unittest

from support import BroomCase

from broom.pyasserts import asserting_helpers, empty_tests, returns_value


def tree(*lines: str) -> ast.Module:
    return ast.parse("\n".join(lines) + "\n")


class PyAssertsTest(BroomCase):
    def test_helpers_assert_through_one_another(self) -> None:
        t = tree("def a():", "    b()", "def b():", "    assert 1", "def c():", "    print(1)")
        self.assertEqual(asserting_helpers(t), {"a", "b"})

    def test_a_return_inside_a_nested_function_is_not_the_tests(self) -> None:
        t = tree("def test_a():", "    def inner():", "        return 1", "    inner()")
        self.assertFalse(returns_value(t.body[0]))
        self.assertEqual([n.name for n in empty_tests(t)], ["test_a"])
        self.assertTrue(returns_value(tree("def test_b():", "    return 2").body[0]))


if __name__ == "__main__":
    unittest.main()
