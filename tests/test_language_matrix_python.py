"""The language matrix for Python: one sample per smell. See language_matrix."""

from __future__ import annotations

import language_matrix as matrix
from language_matrix import Sample, repeated, text
from support import py_function

# Pieces, so that this file holds no suppression, TODO or skip of its own.
SUPPRESS = "# no" + "qa"
TODO = "# TO" + "DO: later"
SKIP = "@unittest." + "skip"
CLONE = py_function("one", 40).split("\n", 1)[1]
CYCLE = {"pkg/__init__.py": "", "pkg/a.py": "X = 1\n", "pkg/b.py": "from pkg import a\n\nY = a.X\n"}
LAYERS = {"pkg/__init__.py": "", "pkg/auth/__init__.py": "", "pkg/auth/login.py": "VALUE = 1\n",
          "pkg/providers/__init__.py": "", "pkg/providers/github.py": "from pkg.auth import login\n\nT = login.VALUE\n",
          "pkg/ui/__init__.py": "", "pkg/ui/view.py": "from pkg.providers import github\n\nSHOWN = github.T\n"}
UTIL = "def helper():\n    return 1\n"
TEST_BASE = text("import unittest", "", "", "class T(unittest.TestCase):", "    def test_old(self):", "        pass")
RUFF = ("ruff",)

SAMPLES = {
    "function_lines": Sample({"a.py": py_function("long_one", 60)}),
    "file_lines": Sample({"a.py": repeated("x{i} = {i}", 450)}),
    "params": Sample({"a.py": text("def many(a, b, c, d, e, f, g):", "    return a")}, RUFF),
    "nesting": Sample({"a.py": text("def deep(x):", "    for a in x:", "        for b in a:", "            for c in b:",
                                    "                for d in c:", "                    for e in d:",
                                    "                        return e")}, RUFF),
    "complexity": Sample({"a.py": text("def branchy(x):", *(f"    if x == {i}:\n        return {i}" for i in range(12)),
                                       "    return x")}, RUFF),
    "nested_ternary": Sample({"a.py": text("def f(x):", "    return 1 if x else (2 if x > 1 else 3)")}),
    "type_lines": Sample({"a.py": "class Big:\n" + repeated("    v{i} = {i}", 260)}),
    "duplicate_lines": Sample({"b.py": "def two(x):\n" + CLONE}, ("jscpd",), base={"a.py": "def one(x):\n" + CLONE}),
    "dead_code": Sample({"pkg/util.py": UTIL + "\n\ndef orphan():\n    return 2\n"}, ("jscpd",),
                        base={"main.py": "from pkg.util import helper\n\nprint(helper())\n", "pkg/__init__.py": "",
                              "pkg/util.py": UTIL}),
    "suppression": Sample({"a.py": f"x = 1  {SUPPRESS}\n"}, RUFF),
    "swallowed_error": Sample({"a.py": text("def f(x):", "    try:", "        return int(x)", "    except Exception:",
                                            "        pass")}, RUFF),
    "commented_code": Sample({"a.py": text("# y = compute(1, 2)", "x = 1")}, RUFF),
    "unused_params": Sample({"a.py": text("def f(a, unused):", "    return a")}, RUFF),
    "magic_numbers": Sample({"a.py": text("def f(x):", "    if x > 86400:", "        return 1", "    return 0")}, RUFF),
    "debug_output": Sample({"a.py": text("def f(x):", '    print("x is", x)', "    return x")}, RUFF),
    "todo": Sample({"a.py": f"{TODO}\nx = 1\n"}, RUFF),
    "type_escape": Sample({"a.py": text("from typing import Any", "", "", "def f(a: Any) -> int:", "    return 1")},
                          RUFF),
    "globals": Sample({"a.py": text("counter = 0", "", "", "def bump():", "    global counter", "    counter += 1")},
                      RUFF),
    "bool_params": Sample({"a.py": text("def f(a: int, flag: bool) -> int:", "    return a if flag else 0")}, RUFF),
    "broad_test_asserts": Sample({"tests/test_a.py": text("import pytest", "", "", "def test_a():",
                                                          "    with pytest.raises(ValueError):",
                                                          "        int('x')")}, RUFF),
    "broad_catch": Sample({"a.py": text("def f(x):", "    try:", "        return int(x)", "    except Exception:",
                                        "        return 0")}, RUFF),
    "missing_docs": Sample({"a.py": text('"""A module."""', "", "", "def fresh(x):", "    return x")}, RUFF),
    "import_cycle": Sample({"pkg/a.py": "from . import b\n\nX = b.Y\n"}, base=CYCLE),
    "folder_cycle": Sample({"pkg/auth/login.py": "from pkg.ui import view\n\nVALUE = view.SHOWN\n"}, base=LAYERS),
    "skipped_test": Sample({"tests/test_a.py": TEST_BASE + f"\n\n    {SKIP}(\"later\")\n    def test_new(self):\n"
                                                           "        pass\n"}, base={"tests/test_a.py": TEST_BASE}),
    "untested_file": Sample({"pkg/fresh.py": repeated("X{i} = {i}", 30)}),
    "deprecated_api": Sample({"t.py": text("import unittest", "", "", "class T(unittest.TestCase):",
                                           "    def test_a(self):", "        self.assertEquals(1, 1)")}, RUFF),
}


class PythonMatrix(matrix.MatrixCase):
    SAMPLES = SAMPLES
