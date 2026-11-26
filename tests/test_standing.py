"""A smell that stands in code no change touches is accepted with the user's agreement (decision 047): `broom smells`
and `broom diagnose` leave it out and say how many, it comes back when its code changes, and a known issue never
expires (decision 046)."""

from __future__ import annotations

import json
import time
import unittest

from support import HAS_PY, BroomCase, py_function

from broom import gate

WHY = "a day in seconds"
TWO = "def f(x):\n    if x > 86400:\n        return 1\n    if x > 3600:\n        return 2\n    return x\n"


class StandingTest(BroomCase):
    def smells(self, r, *args: str) -> dict:
        out = self.cli(r, "smells", "--json", *(args or ("--only", "function_lines")))
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def accept(self, r, *args: str):
        return self.cli(r, "known", "--accept", WHY, *args)

    def test_a_long_function_accepted_by_its_line_is_left_out_and_counted_until_it_grows(self) -> None:
        r = self.repo({"a.py": py_function("long", 60), "b.py": py_function("other", 60)})
        self.assertEqual(self.smells(r)["total"], 2)
        out = self.accept(r, "--agreed", "--smell", "function_lines", "a.py:1")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("accepted 1 standing function_lines smell(s)", out.stdout)
        data = self.smells(r)
        self.assertEqual((data["total"], data["known"], [s["file"] for s in data["smells"]]), (1, 1, ["b.py"]))
        self.assertIn("1 smell(s) accepted as known hidden", self.cli(r, "smells", "--only", "function_lines").stdout)
        self.assertIn("(a day in seconds; the user agreed)", self.cli(r, "known").stdout)
        (r / "a.py").write_text(py_function("long", 61))
        self.assertEqual((self.smells(r)["total"], self.smells(r)["known"]), (2, 0), "it grew: its code changed")

    def test_without_the_users_agreement_or_a_place_nothing_is_accepted(self) -> None:
        r = self.repo({"a.py": py_function("long", 60)})
        for args, says in ((("--smell", "function_lines", "a.py"), "only with the user's agreement"),
                           (("--agreed", "--smell", "function_lines"), "say why and where"),
                           (("--agreed", "--smell", "params", "a.py"), "no params that isn't known already")):
            with self.subTest(args=args):
                out = self.accept(r, *args)
                self.assertEqual(out.returncode, 1, args)
                self.assertIn(says, out.stdout + out.stderr)
        out = self.cli(r, "known", "--smell", "function_lines", "a.py")
        self.assertIn("--smell goes with --accept", out.stderr)
        self.assertEqual((self.smells(r)["total"], gate.baseline_load()), (1, {}))

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_one_occurrence_is_accepted_and_the_others_in_its_file_still_count(self) -> None:
        r = self.repo({"a.py": TWO})
        self.assertEqual(self.smells(r, "--only", "magic_numbers")["smells"][0]["text"],
                         "2 magic number(s) at line(s) 2, 4")
        self.assertEqual(self.accept(r, "--agreed", "--smell", "magic_numbers", "a.py:2").returncode, 0)
        data = self.smells(r, "--only", "magic_numbers")
        self.assertEqual((data["known"], data["smells"][0]["text"]), (1, "1 magic number(s) at line(s) 4"))
        (r / "a.py").write_text(TWO.replace("86400", "86401"))
        self.assertEqual(self.smells(r, "--only", "magic_numbers")["known"], 0, "its line changed")

    def test_the_diagnosis_leaves_an_accepted_smell_out_and_counts_it(self) -> None:
        r = self.repo({"a.py": py_function("long", 60)})
        self.assertEqual(self.accept(r, "--agreed", "--smell", "function_lines", "a.py").returncode, 0)
        data = json.loads(self.cli(r, "diagnose", "--json").stdout)
        self.assertEqual(([k["smell"] for k in data["by_smell"] if k["smell"] == "function_lines"],
                          data["summary"]["known"]), ([], 1))
        self.assertIn("accepted as known, hidden", self.cli(r, "diagnose").stdout)

    def test_a_known_issue_never_expires(self) -> None:
        old = {"t": time.time() - 400 * 86400, "file": "/gone/a.py", "line": 1, "tool": "ruff", "rule": "X", "msg": "m"}
        gate.baseline_add_entries({"old": old})
        gate.baseline_add_entries({"new": {**old, "t": time.time()}})
        self.assertEqual(set(gate.baseline_load()), {"old", "new"})
