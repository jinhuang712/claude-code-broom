"""`broom report`: what the ledger says broom stopped, fixed and let through, and how long its checks took."""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

from test_ledger import DAY, LedgerCase, lines
from support import py_function

from broom import ledger


class ReportTest(LedgerCase):
    def row(self, repo: Path, event: str, key: str, rule: str = "F401", tool: str = "ruff", **more: object) -> dict:
        return {"t": time.time(), "repo": str(repo), "event": event, "where": "commit", "key": key, "tool": tool,
                "rule": rule, "file": "a.py", **more}

    def fill(self, r: Path) -> None:
        old = time.time() - 40 * DAY
        rows = [self.row(r, "block", "k1"), self.row(r, "block", "k1"), self.row(r, "fix", "k1"),
                self.row(r, "block", "k2"), self.row(r, "pass", "k2", how="retry"),
                self.row(r, "block", "k3", "function_lines", "smells"),
                self.row(r, "pass", "k3", "function_lines", "smells", how="accept", why="legacy"),
                self.row(r, "block", "k4", "function_lines", "smells"),
                {**self.row(r, "block", "k5"), "t": old}, {**self.row(r, "fix", "k5"), "t": old},
                self.row(Path("/elsewhere"), "block", "k6"),
                {"t": time.time(), "repo": str(r), "event": "skip", "tool": "ruff", "note": "missing:ruff (x)"},
                {"t": time.time(), "repo": str(r), "event": "skip", "tool": "ruff", "note": "missing:ruff (x)"},
                {"t": time.time(), "repo": str(r), "event": "skip", "tool": "ruff", "note": "timeout:ruff in /x"}]
        rows += [{"t": time.time(), "repo": str(r), "event": "time", "check": c, "seconds": s}
                 for c, s in (("ruff", 0.1), ("ruff", 0.3), ("ruff", 0.5), ("go", 2.0))]
        rows += [{"t": time.time(), "repo": str(r), "event": "run", "where": w, "seconds": s}
                 for w, s in (("commit", 2.0), ("pre-commit", 4.0), ("stop", 1.0))]
        ledger.write(rows)

    def report(self, cwd: Path, *args: str) -> dict:
        out = self.cli(cwd, "report", "--json", *args)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_the_text_says_what_was_blocked_fixed_and_let_through(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.fill(r)
        out = self.cli(r, "report")
        self.assertEqual(out.returncode, 0, out.stderr)
        text = out.stdout
        self.assertIn("blocked 4, fixed 1, let through 2, still open 1, fix rate 33%", text)
        rule = {words[0]: line for line in text.splitlines() if (words := line.split())}
        self.assertEqual(rule["F401"].split(), ["F401", "ruff", "2", "1", "1", "(retry", "1)", "0", "50%"])
        self.assertEqual(rule["function_lines"].split(), ["function_lines", "smells", "2", "0", "1", "(accept", "1)",
                                                           "1", "0%"])
        self.assertIn("ruff: 3 (missing 2, timeout 1)", text)
        self.assertIn("ruff: median 0.3, max 0.5 (3 runs)", text)
        self.assertIn("go: median 2.0, max 2.0 (1 run)", text)
        self.assertIn("at a commit: median 3.0, max 4.0 (2 runs)", text)
        self.assertIn("at a turn's end: median 1.0, max 1.0 (1 run)", text)

    def test_json_gives_the_same_and_the_period_and_the_repos_are_chosen(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.fill(r)
        data = self.report(r)
        self.assertEqual((data["repos"], data["blocked"], data["fixed"], data["let_through"], data["open"]),
                         ([str(r)], 4, 1, 2, 1))
        self.assertEqual(data["fix_rate"], round(1 / 3, 3))
        self.assertEqual(data["how"], {"retry": 1, "accept": 1})
        rules = {x["rule"]: x for x in data["rules"]}
        self.assertEqual((rules["F401"]["fix_rate"], rules["function_lines"]["fix_rate"]), (0.5, 0.0))
        self.assertEqual(data["skips"], {"ruff": {"missing": 2, "timeout": 1}})
        self.assertEqual(data["seconds"]["ruff"], {"runs": 3, "median": 0.3, "max": 0.5})
        self.assertEqual(self.report(r, "--days", "60")["blocked"], 5, "the finding of 40 days ago counts in 60")
        every = self.report(r, "--all")
        self.assertEqual((every["repos"], every["blocked"], every["left_out"]), ("all", 1, 1),
                         "the other repo counts, and this one, in a temporary folder, is left out")
        self.assertIn("every repo but 1 in a temporary folder", self.cli(r, "report", "--all").stdout)

    def test_since_a_day_replaces_the_days(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.fill(r)
        day = time.strftime("%Y-%m-%d", time.localtime(time.time() - 45 * DAY))
        data = self.report(r, "--since", day)
        self.assertEqual((data["since"], data["blocked"]), (day, 5), "the finding of 40 days ago is after that day")
        self.assertEqual(self.report(r, "--since", time.strftime("%Y-%m-%d"))["blocked"], 4)
        self.assertIn(f"since {day}", self.cli(r, "report", "--since", day).stdout)
        self.assertEqual(self.cli(r, "report", "--since", "last week").returncode, 2)

    def test_a_check_that_ran_a_tool_leaves_its_whole_seconds_once(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("x = 2\n")
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        (run,) = lines("run")
        self.assertEqual((run["where"], run["repo"]), ("commit", str(r)))
        self.assertIsInstance(run["seconds"], float)
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(len(lines("run")), 1, "content that passed already runs no tool")
        self.assertEqual(self.report(r)["checks"]["at a commit"]["runs"], 1)

    def test_old_lines_with_a_how_that_no_longer_occurs_are_still_read(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        ledger.write([self.row(r, e, k, **({"how": how} if e == "pass" else {}))
                      for k, how in (("k1", "retry"), ("k2", "denials"), ("k3", "stop-again")) for e in ("block", "pass")])
        data = self.report(r)
        self.assertEqual((data["blocked"], data["let_through"], data["how"]),
                         (3, 3, {"retry": 1, "denials": 1, "stop-again": 1}))
        self.assertIn("(denials 1, retry 1, stop-again 1)", self.cli(r, "report").stdout)

    def test_a_finding_blocked_three_times_and_then_fixed_counts_once(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        for _ in range(3):
            self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        (r / "a.py").write_text(py_function("small", 20))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(len(lines("block")), 3)
        data = self.report(r)
        self.assertEqual((data["blocked"], data["fixed"], data["let_through"], data["open"], data["fix_rate"]),
                         (1, 1, 0, 0, 1.0))
        self.assertEqual([(x["rule"], x["blocked"], x["fixed"]) for x in data["rules"]], [("function_lines", 1, 1)])

    def test_paths_narrow_the_report_to_those_files(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "sub/b.py": "x = 1\n"})
        rows = [{**self.row(r, "block", "k1"), "file": "a.py"}, {**self.row(r, "block", "k2"), "file": "sub/b.py"}]
        ledger.write(rows)
        self.assertEqual(self.report(r, "sub")["blocked"], 1)
        self.assertEqual(self.report(r, "a.py", "sub/b.py")["blocked"], 2)

    def test_outside_a_repo_report_fails_unless_it_is_asked_for_every_repo(self) -> None:
        out = self.cli(self.tmp, "report")
        self.assertEqual(out.returncode, 1)
        self.assertIn("not inside a git repository", out.stderr)
        self.assertEqual(self.cli(self.tmp, "report", "--all").returncode, 0)
        self.assertIn("nothing recorded", self.cli(self.tmp, "report", "--all").stdout)

    def test_a_repo_and_its_linked_worktrees_share_one_record(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        wt = self.tmp / "side"
        self.sh(r, "git", "worktree", "add", "-q", str(wt), "-b", "side")
        self.huge(wt)
        self.assertTrue(self.denied(self.commit(wt, "git commit -m x")))
        (block,) = lines("block")
        self.assertEqual((block["repo"], block["file"]), (str(r), "a.py"), "main root; own file")
        self.assertEqual(self.report(r)["blocked"], 1, "from the main checkout")
        self.assertEqual(self.report(wt)["blocked"], 1, "from the linked worktree")
        self.assertEqual(self.report(wt)["repos"], [str(r)])
        (wt / "a.py").write_text(py_function("small", 20))
        self.sh(wt, "git", "add", "a.py")
        self.assertEqual(self.commit(wt, "git commit -m x"), {})
        self.assertEqual([x["repo"] for x in lines("fix")], [str(r)])
        self.assertEqual(self.report(r)["fixed"], 1)


if __name__ == "__main__":
    unittest.main()
