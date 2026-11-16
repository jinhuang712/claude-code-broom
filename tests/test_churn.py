"""Hotspots by churn: a file's score is its smells times the commits that touched it lately, `--by smells` keeps the
old order, a repo with no history falls back to it and says so, and the session note names the files in the churn
order."""

from __future__ import annotations

import json
from pathlib import Path

from gitwork import GitWork
from support import py_function

from broom.hotspots import rank, score
from broom.smell import Smell

LONG = py_function("stale", 120)  # one smell past the hard limit
BUSY = py_function("busy", 60).replace("+=", "-=")  # one hint, and not a copy of the other


def hints(name: str, count: int) -> str:
    """`count` functions of 60 lines, one hint each, no two alike."""
    ops = ["+=", "-=", "*=", "|=", "^=", "&="]
    return "".join(py_function(f"{name}{i}", 60).replace("+=", ops[i]) + "\n\n" for i in range(count))


class ChurnTest(GitWork):
    def setUp(self) -> None:
        super().setUp()
        self.bare = self.fake_path()  # no linter and no jscpd: what is found is the same on every machine

    def busy_repo(self) -> Path:
        """`stale.py` (one severe smell) untouched since 2020 and `busy.py` (one hint) committed three times lately."""
        return self.history_repo([(2000, {"stale.py": LONG}), (30, {"busy.py": BUSY}),
                                  (20, {"busy.py": BUSY + "\n\nB = 1\n"}), (10, {"busy.py": BUSY + "\n\nB = 2\n"})])

    def hotspots(self, r: Path, *args: str) -> dict:
        done = self.cli(r, "smells", "--json", *args, env=self.bare)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def history_notes(self, data: dict) -> list:
        return [n for n in data["notes"] if not n.startswith("missing:")]

    def test_the_score_is_the_smells_times_one_more_than_the_changes(self) -> None:
        self.assertEqual(score(2, 3, 4), (3 * 2 + 3) * 5)
        self.assertEqual(score(0, 0, 9), 0, "a file with no smell costs nothing however often it changes")
        self.assertEqual(score(1, 0, 0), 3)

    def test_a_bad_file_that_changes_comes_before_a_worse_one_nobody_touches(self) -> None:
        data = self.hotspots(self.busy_repo())
        rows = {f["file"]: f for f in data["hotspots"]}
        self.assertEqual(data["by"], "churn")
        self.assertEqual([f["file"] for f in data["hotspots"]], ["busy.py", "stale.py"])
        self.assertEqual((rows["busy.py"]["changes"], rows["stale.py"]["changes"]), (3, 0))
        for f in rows.values():
            self.assertEqual(f["score"], (3 * f["severe"] + f["hints"]) * (1 + f["changes"]))
        self.assertGreater(rows["busy.py"]["score"], rows["stale.py"]["score"])
        self.assertEqual(rows["stale.py"]["severe"], 1)

    def test_by_smells_keeps_the_old_order_and_the_same_numbers(self) -> None:
        r = self.busy_repo()
        old = self.hotspots(r, "--by", "smells")
        self.assertEqual((old["by"], [f["file"] for f in old["hotspots"]]), ("smells", ["stale.py", "busy.py"]))
        self.assertEqual(old["hotspots"][1]["changes"], 3, "the numbers are the same, only the order differs")
        self.assertEqual(self.history_notes(old), [])

    def test_the_text_rows_show_changes_and_score(self) -> None:
        out = self.cli(self.busy_repo(), "smells", env=self.bare).stdout
        row = next(r for r in out.splitlines() if r.startswith("  busy.py"))
        self.assertRegex(row, r"busy\.py  0 severe, 1 hints, 3 changes, score 4; worst: ")
        self.assertIn("Hotspots, by score", out)
        self.assertIn("Hotspots, most severe first", self.cli(self.busy_repo(), "smells", "--by", "smells", env=self.bare).stdout)

    def test_no_history_falls_back_to_the_old_order_and_says_so(self) -> None:
        # Four hints score 4 and one severe smell scores 3: by score the first would lead, by smells the second.
        r = self.history_repo([(2000, {"many.py": hints("m", 4), "stale.py": LONG})])
        data = self.hotspots(r)
        self.assertEqual((data["by"], [f["file"] for f in data["hotspots"]]), ("smells", ["stale.py", "many.py"]))
        self.assertEqual([f["changes"] for f in data["hotspots"]], [0, 0])
        self.assertEqual(self.history_notes(data),
                         ["no commits in the last 90 days, or git log failed: the hotspots are ordered by their smells"])
        self.assertIn("note: no commits in the last 90 days", self.cli(r, "smells", env=self.bare).stdout)
        self.assertEqual(self.history_notes(self.hotspots(r, "--by", "smells")), [], "nothing to say when asked for")

    def test_a_repo_with_no_commit_has_no_history_either(self) -> None:
        r = self.tmp / "fresh"
        r.mkdir()
        self.sh(r, "git", "init", "-q")
        (r / "a.py").write_text(LONG)
        data = self.hotspots(r)
        self.assertEqual((data["by"], data["hotspots"][0]["changes"]), ("smells", 0))
        self.assertTrue(any("no commits" in n for n in data["notes"]))

    def test_the_session_note_names_the_worst_files_in_the_churn_order(self) -> None:
        r = self.busy_repo()
        note = self.session(r, "s1", self.bare, "session-scan")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("worst files: busy.py, stale.py", note)

    def test_rank_orders_by_the_score_or_by_the_smells(self) -> None:
        repo = self.tmp

        def smell(name: str, level: str) -> Smell:
            return Smell(repo, repo / name, 1, "function_lines", "f", 120, None, "ast", level, 100)

        found = [smell("stale.py", "block"), smell("busy.py", "hint")]
        churn = {"busy.py": 3}
        self.assertEqual([f["file"] for f in rank(found, churn, "churn")[1]], ["busy.py", "stale.py"])
        self.assertEqual([f["file"] for f in rank(found, churn, "smells")[1]], ["stale.py", "busy.py"])
        self.assertEqual([f["file"] for f in rank(found, {}, "smells")[1]], ["stale.py", "busy.py"])
        self.assertEqual(rank(found, churn, "churn")[1][0]["score"], 4)
