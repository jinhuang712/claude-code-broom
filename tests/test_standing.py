"""A smell that stands in code no change touches is accepted with the user's agreement (decision 047): `broom smells`
and `broom diagnose` collapse it, leave it out of their lists and still count it, it comes back when its code changes,
and a known issue never expires (decision 046). What is accepted or dismissed is only collapsed: every total counts
it, and one line says how many; a check with nothing else to say stays silent."""

from __future__ import annotations

import json
import time
import unittest

from support import HAS_PY, BroomCase, py_function

from broom import gate, hotspots

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
        self.assertEqual((data["total"], data["hints"], data["known"], data["open"]), (2, 2, 1, 1), "it still counts")
        self.assertEqual([s["file"] for s in data["smells"]], ["b.py"], "and is not listed")
        first = self.cli(r, "smells", "--only", "function_lines").stdout.splitlines()[0]
        self.assertIn("2 code smell(s) of function_lines in ", first)
        self.assertTrue(first.endswith(": 0 past the hard limit, 2 hints, 0 nits; 1 accepted as known, collapsed."), first)
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
        self.assertEqual((data["total"], data["known"], data["smells"][0]["text"]),
                         (2, 1, "1 magic number(s) at line(s) 4"))
        (r / "a.py").write_text(TWO.replace("86400", "86401"))
        self.assertEqual(self.smells(r, "--only", "magic_numbers")["known"], 0, "its line changed")

    def test_the_diagnosis_leaves_an_accepted_smell_out_and_counts_it(self) -> None:
        r = self.repo({"a.py": py_function("long", 60)})
        before = json.loads(self.cli(r, "diagnose", "--json").stdout)["summary"]
        self.assertEqual(self.accept(r, "--agreed", "--smell", "function_lines", "a.py").returncode, 0)
        data = json.loads(self.cli(r, "diagnose", "--json").stdout)
        self.assertEqual([k["smell"] for k in data["by_smell"] if k["smell"] == "function_lines"], [])
        summary = data["summary"]
        self.assertEqual((summary["smells"], summary["hints"], summary["known"], summary["open"]),
                         (before["smells"], before["hints"], 1, before["smells"] - 1))
        self.assertIn("accepted as known, collapsed", self.cli(r, "diagnose").stdout)

    def test_the_session_note_counts_known_smells_and_a_dismissed_one_keeps_its_count(self) -> None:
        data = {"head": "h", "total": 9, "severe": 4, "known": 3, "open_severe": 2, "hotspots": ["a.py"]}
        self.assertIn("4 code smell(s) past the hard limit in this repo (9 in all; 3 accepted as known, collapsed;",
                      hotspots.session_note(self.tmp, data))
        self.assertIn("in all; 3 accepted as known, collapsed). Don't raise a cleanup",
                      hotspots.session_note(self.tmp, {**data, "open_severe": 0}), "every severe one is accepted")
        hotspots.DISMISSED.parent.mkdir(parents=True, exist_ok=True)
        hotspots.DISMISSED.write_text(json.dumps({str(self.tmp): 4}))
        self.assertEqual(hotspots.session_note(self.tmp, data),
                         "broom: 4 code smell(s) past the hard limit in this repo (9 in all; 3 accepted as known, "
                         "collapsed). Don't raise a cleanup for them.")
        self.assertIn("clean skill", hotspots.session_note(self.tmp, {**data, "severe": 5}), "the count grew")

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_a_known_issue_counts_in_sweep_and_a_check_that_speaks_says_how_many_it_collapsed(self) -> None:
        r = self.repo({"a.py": "x = 1\n", ".broom.json": '{"smells": "off"}'})  # lint alone
        (r / "a.py").write_text("import os\n\nx = 1\n")
        self.sh(r, "git", "add", "a.py")
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.cli(r, "known", "--accept", WHY).returncode, 0)
        swept = self.cli(r, "sweep", "--check")
        self.assertIn("[broom] 1 issue(s) in the changed lines; 1 accepted as known, collapsed", swept.stdout)
        self.assertEqual(swept.returncode, 0, "a known issue counts, and fails nothing")
        self.assertEqual(self.commit(r, "git commit -m x"), {}, "a check with nothing to say stays silent")
        (r / "a.py").write_text("import os\nimport sys\n\nx = 1\n")
        self.sh(r, "git", "add", "a.py")
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("Commit blocked: 1 issue(s)", reason, "a known issue never blocks")
        self.assertIn("broom: 1 issue(s) accepted as known in the checked files, collapsed", reason)

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_a_turn_end_block_says_how_many_known_issues_it_collapsed(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("import os\n\nx = 1\n")
        self.sh(r, "git", "add", "a.py")
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.cli(r, "known", "--accept", WHY).returncode, 0)
        (r / "a.py").write_text("import os\nimport sys\n\nx = 1\n")
        edit = {"session_id": "s9", "cwd": str(r), "tool_name": "Edit", "tool_input": {"file_path": str(r / "a.py")}}
        self.hook("edit", edit)
        out = self.hook("stop", {"session_id": "s9", "cwd": str(r), "permission_mode": "default"})
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("1 issue(s) accepted as known in the checked files, collapsed", out["reason"])

    def test_a_known_issue_never_expires(self) -> None:
        old = {"t": time.time() - 400 * 86400, "file": "/gone/a.py", "line": 1, "tool": "ruff", "rule": "X", "msg": "m"}
        gate.baseline_add_entries({"old": old})
        gate.baseline_add_entries({"new": {**old, "t": time.time()}})
        self.assertEqual(set(gate.baseline_load()), {"old", "new"})
