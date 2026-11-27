"""Nits are counted apart from hints, weigh 0 in a file's score, and a smell row lists every line of an occurrence."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from support import BroomCase

from broom.hotspots import counts, order_text, rank, render
from broom.smells import Smell

REPO = Path("/r")


def smell(rel: str, level: str, metric: str = "todo", *, added: tuple = ()) -> Smell:
    return Smell(REPO, REPO / rel, (added or (1,))[0], metric, "k", max(1, len(added)), None, "ruff", level, 0,
                 added=list(added))


class CountsTest(unittest.TestCase):
    def test_hints_and_nits_are_counted_apart_and_the_known_ones_count_too(self) -> None:
        kept = [smell("a.py", "block", "function_lines"), smell("a.py", "hint", "function_lines"), smell("b.py", "nit")]
        hidden = [smell("b.py", "nit", "magic_numbers")]
        self.assertEqual(counts(kept, hidden), {"total": 4, "severe": 1, "hints": 1, "nits": 2, "known": 1, "open": 3})

    def test_the_headline_gives_hints_and_nits_apart(self) -> None:
        data = {"repo": "/r", "base": None, "total": 244, "severe": 0, "hints": 6, "nits": 238, "known": 5,
                "notes": [], "smells": [], "hotspots": [], "by": "smells"}
        self.assertEqual(render(data), "[broom] 244 code smell(s) in /r: 0 past the hard limit, 6 hints, 238 nits; "
                                       "5 accepted as known, collapsed.")

    def test_a_file_row_counts_its_nits_and_they_weigh_nothing_in_its_score(self) -> None:
        rows = [smell("a.py", "hint", "function_lines")] + [smell("a.py", "nit")] * 4
        _, files = rank(rows, {"a.py": 1}, "churn")
        self.assertEqual([(f["hints"], f["nits"], f["score"]) for f in files], [(1, 4, 2)])

    def test_a_file_of_nits_alone_is_no_hotspot_and_its_smells_stay_listed(self) -> None:
        rows = [smell("a.py", "nit"), smell("b.py", "nit", "magic_numbers"), smell("b.py", "hint", "function_lines")]
        ordered, files = rank(rows, {"a.py": 9, "b.py": 0}, "churn")
        self.assertEqual(len(ordered), 3, "every smell is still listed")
        self.assertEqual([f["file"] for f in files], ["b.py"])
        self.assertIn("code lines long", files[0]["worst"], "the worst of a file is never a nit while it has a hint")
        self.assertEqual(rank(rows[:2], {}, "smells")[1], [])

    def test_the_formula_line_says_nits_weigh_0(self) -> None:
        self.assertEqual(order_text("churn", 50),
                         "by score = (3 x severe + hints) x (1 + changes in the last 50 commits); nits weigh 0")

    def test_the_report_of_nits_alone_lists_the_smells_without_a_hotspots_list(self) -> None:
        one = {"file": "a.py", "line": 1, "smell": "todo", "text": "1 TODO/FIXME comment(s) at line(s) 1"}
        data = {"repo": "/r", "base": None, "total": 1, "severe": 0, "hints": 0, "nits": 1, "notes": [],
                "smells": [one], "by": "churn", "hotspots": []}
        text = render(data)
        self.assertIn("Worst smells:\n  a.py:1  todo", text)
        self.assertNotIn("Hotspots", text)


class NitsEndToEndTest(BroomCase):
    def test_smells_json_and_text_count_nits_apart(self) -> None:
        env = self.fake_path(("ruff",))
        r = self.repo({"a.py": '"""Doc."""\nx = 1  # TODO: one\ny = 2  # TODO: two\n'})
        data = json.loads(self.cli(r, "smells", "--json", env=env).stdout)
        self.assertEqual((data["hints"], data["nits"]), (0, data["total"]))
        text = self.cli(r, "smells", env=env).stdout
        self.assertIn(f"0 hints, {data['total']} nits", text)
        self.assertEqual((data["hotspots"], len(data["smells"])), ([], 1), "listed as a smell, not a hotspot")
        self.assertNotIn("Hotspots", text)


if __name__ == "__main__":
    unittest.main()
