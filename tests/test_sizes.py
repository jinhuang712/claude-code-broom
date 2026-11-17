"""`broom smells --only function_lines` (or `type_lines`) goes on past the smells with the longest that aren't."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from support import HAS_GO, HAS_PY, HAS_TS, BroomCase, py_function

from broom.rowcache import RowCache
from broom.sizes import lowered

LIMITS = {"function_lines": (50, 100), "type_lines": (250, 1_000_000)}


def py_class(name: str, lines: int) -> str:
    """A Python class `lines` long."""
    return f"class {name}:\n" + "".join(f"    a{i} = {i}\n" for i in range(lines - 1))


def ts_function(name: str, lines: int) -> str:
    """A TypeScript function `lines` long."""
    body = "".join(f"  x += {i};\n" for i in range(lines - 3))
    return f"export function {name}(x: number): number {{\n{body}  return x;\n}}\n"


def go_function(name: str, lines: int) -> str:
    """A Go function `lines` long."""
    body = "".join(f"\tx += {i}\n" for i in range(lines - 3))
    return f"func {name}(x int) int {{\n{body}\treturn x\n}}\n"


class SizesTest(BroomCase):
    def smells(self, r: Path, *args: str) -> dict:
        """What `broom smells --json` says with `args`."""
        out = self.cli(r, "smells", "--json", *args)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def python_repo(self) -> Path:
        """A repo with a function of 120, 60, 30, 20 and 10 lines, each in a file of its own."""
        return self.repo({f"{name}.py": py_function(name, lines)
                          for name, lines in (("huge", 120), ("big", 60), ("mid", 30), ("small", 20), ("tiny", 10))})

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_the_longest_functions_are_listed_smells_first_then_sizes(self) -> None:
        r = self.python_repo()
        data = self.smells(r, "--only", "function_lines", "--top", "5")
        self.assertEqual([(s["file"], s["level"]) for s in data["smells"]], [("huge.py", "block"), ("big.py", "hint")])
        self.assertEqual([(s["file"], s["name"], s["value"]) for s in data["sizes"]],
                         [("mid.py", "mid", 30), ("small.py", "small", 20), ("tiny.py", "tiny", 10)])
        self.assertEqual({k for s in data["sizes"] for k in s}, {"file", "line", "name", "value"})
        self.assertEqual((data["total"], data["severe"], data["hints"]), (2, 1, 1), "sizes are not smells")
        self.assertEqual([f["file"] for f in data["hotspots"]], ["huge.py", "big.py"], "nor are they hotspots")
        text = self.cli(r, "smells", "--only", "function_lines", "--top", "5").stdout.splitlines()
        self.assertIn("2 code smell(s) of function_lines", text[0])
        self.assertEqual(text[-4:], ["Longest under the limit (not smells):",
                                     "  mid.py:1  function_lines  mid is 30 lines long",
                                     "  small.py:1  function_lines  small is 20 lines long",
                                     "  tiny.py:1  function_lines  tiny is 10 lines long"])

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_sizes_fill_only_what_top_leaves_after_the_smells(self) -> None:
        r = self.python_repo()
        self.assertEqual(self.smells(r, "--only", "function_lines", "--top", "2")["sizes"], [])
        self.assertEqual([s["name"] for s in self.smells(r, "--only", "function_lines", "--top", "3")["sizes"]], ["mid"])
        self.assertEqual(len(self.smells(r, "--only", "function_lines", "--top", "9")["sizes"]), 3)
        self.assertEqual(self.smells(r, "--only", "function_lines", "--top", "0")["sizes"], [])

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_a_repo_with_no_smell_still_lists_its_longest(self) -> None:
        r = self.repo({"a.py": py_function("one", 30), "b.py": py_function("two", 20).replace("+=", "-=")})
        data = self.smells(r, "--only", "function_lines", "--top", "5")
        self.assertEqual((data["total"], data["smells"], [s["name"] for s in data["sizes"]]), (0, [], ["one", "two"]))
        text = self.cli(r, "smells", "--only", "function_lines", "--top", "1").stdout
        self.assertIn("  a.py:1  function_lines  one is 30 lines long", text)
        self.assertNotIn("two", text)

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_sizes_are_listed_for_one_of_the_two_kinds_and_nowhere_else(self) -> None:
        r = self.python_repo()
        plain = self.cli(r, "smells").stdout
        self.assertNotIn("sizes", self.smells(r))
        self.assertNotIn("sizes", self.smells(r, "--only", "file_lines"))
        self.assertNotIn("sizes", self.smells(r, "--only", "function_lines", "--only", "type_lines"))
        self.assertNotIn("sizes", self.smells(r, "--only", "function_lines", "--base", "HEAD"))
        self.smells(r, "--only", "function_lines", "--top", "5")
        self.assertEqual(self.cli(r, "smells").stdout, plain, "rows measured for sizes never reach a normal run")
        self.assertEqual(self.cli(r, "smells", "--only", "function_lines").stdout.count("Longest under"), 1)

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_the_longest_types_are_listed_the_same_way(self) -> None:
        r = self.repo({"big.py": py_class("Big", 300), "mid.py": py_class("Mid", 120), "small.py": py_class("Small", 40)})
        data = self.smells(r, "--only", "type_lines", "--top", "5")
        self.assertEqual([s["smell"] for s in data["smells"]], ["type_lines"])
        self.assertEqual([(s["name"], s["value"]) for s in data["sizes"]], [("Mid", 120), ("Small", 40)])
        self.assertEqual(data["total"], 1)

    def test_the_rows_of_a_list_of_sizes_are_kept_apart_from_the_normal_ones(self) -> None:
        low = lowered(LIMITS, "function_lines")
        self.assertEqual(low, {"function_lines": (1, 100), "type_lines": (250, 1_000_000)})
        self.assertEqual(LIMITS["function_lines"], (50, 100), "the limits given are left as they were")
        self.assertNotEqual(RowCache(self.tmp, low).key("a.py", "x"), RowCache(self.tmp, LIMITS).key("a.py", "x"))

    @unittest.skipUnless(HAS_TS and shutil.which("node"), "oxlint, tsc or node missing")
    def test_typescript_functions_and_classes_are_listed(self) -> None:
        big = "export class Big {\n" + "".join(f"  m{n}() {{ return this; }}\n" for n in range(260)) + "}\n"
        r = self.repo({"a.ts": ts_function("big", 60), "b.ts": ts_function("mid", 30) + ts_function("tiny", 12),
                       "c.ts": big + "export class Small {\n  a() { return 1; }\n}\n"})
        data = self.smells(r, "--only", "function_lines", "--top", "5")
        self.assertEqual([s["text"].split()[0] for s in data["smells"]], ["big"])
        self.assertEqual([s["name"] for s in data["sizes"]], ["mid", "tiny"])
        types = self.smells(r, "--only", "type_lines", "--top", "5")
        self.assertEqual([(s["name"], s["file"]) for s in types["sizes"]], [("Small", "c.ts")])

    @unittest.skipUnless(HAS_GO, "go tools missing")
    def test_go_functions_are_listed(self) -> None:
        r = self.repo({"go/a.go": "package a\n\n" + "\n".join(go_function(n, size) for n, size in
                                                              (("Big", 70), ("Mid", 25), ("Small", 11)))})
        data = self.smells(r, "--only", "function_lines", "--top", "5")
        self.assertEqual([s["text"].split()[0] for s in data["smells"]], ["Big"])
        self.assertEqual([s["name"] for s in data["sizes"]], ["Mid", "Small"])


if __name__ == "__main__":
    unittest.main()
