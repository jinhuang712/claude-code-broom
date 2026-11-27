"""`broom report`: what the ledger says broom stopped, fixed and let through, and how long its checks took."""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

from test_ledger import LedgerCase, lines
from support import py_function

from broom import ledger


class ReportTest(LedgerCase):
    def row(self, repo: Path, event: str, key: str, rule: str = "F401", tool: str = "ruff", **more: object) -> dict:
        return {"t": time.time(), "repo": str(repo), "event": event, "where": "commit", "key": key, "tool": tool,
                "rule": rule, "file": "a.py", **more}

    def fill(self, r: Path) -> None:
        old = "0.20.0"  # an earlier broom wrote these
        rows = [self.row(r, "block", "k1"), self.row(r, "block", "k1"), self.row(r, "fix", "k1"),
                self.row(r, "block", "k2"), self.row(r, "pass", "k2", how="retry"),
                self.row(r, "block", "k3", "function_lines", "smells"),
                self.row(r, "pass", "k3", "function_lines", "smells", how="accept", why="legacy"),
                self.row(r, "block", "k4", "function_lines", "smells"),
                {**self.row(r, "block", "k5"), "v": old}, {**self.row(r, "fix", "k5"), "v": old},
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
        self.assertIn("in the whole record", text)
        self.assertIn("blocked 5, fixed 2, let through 2, still open 1, fix rate 50%", text)
        rule = {words[0]: line for line in text.splitlines() if (words := line.split())}
        self.assertEqual(rule["F401"].split(), ["F401", "ruff", "3", "2", "1", "(retry", "1)", "0", "67%"])
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
                         ([str(r)], 5, 2, 2, 1))
        self.assertNotIn("days", data)
        self.assertIsNone(data["since"])
        self.assertEqual(data["fix_rate"], 0.5)
        self.assertEqual(data["how"], {"retry": 1, "accept": 1})
        rules = {x["rule"]: x for x in data["rules"]}
        self.assertEqual((rules["F401"]["fix_rate"], rules["function_lines"]["fix_rate"]), (0.667, 0.0))
        self.assertEqual(data["skips"], {"ruff": {"missing": 2, "timeout": 1}})
        self.assertEqual(data["seconds"]["ruff"], {"runs": 3, "median": 0.3, "max": 0.5})
        every = self.report(r, "--all")
        self.assertEqual((every["repos"], every["blocked"], every["left_out"]), ("all", 1, 1),
                         "the other repo counts, and this one, in a temporary folder, is left out")
        self.assertIn("every repo but 1 in a temporary folder", self.cli(r, "report", "--all").stdout)

    def test_since_a_version_keeps_the_lines_that_version_or_a_later_one_wrote(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.fill(r)
        with open(ledger.ledger_of(str(r)), "a") as f:  # a line from before broom marked its lines with a version
            f.write(json.dumps({k: v for k, v in self.row(r, "block", "k0").items()}) + "\n")
        self.assertEqual(self.report(r)["blocked"], 6, "the whole record")
        data = self.report(r, "--since", "0.20.0")
        self.assertEqual((data["since"], data["blocked"]), ("0.20.0", 5), "a line with no version is older than any")
        self.assertEqual(self.report(r, "--since", "0.20.1")["blocked"], 4, "k5 was written by 0.20.0")
        self.assertEqual(self.report(r, "--since", ledger.__version__)["blocked"], 4)
        self.assertEqual(self.report(r, "--since", "999.0")["blocked"], 0)
        self.assertIn("since 0.20.1", self.cli(r, "report", "--since", "0.20.1").stdout)
        self.assertIn("nothing recorded for", self.cli(r, "report", "--since", "999.0").stdout)

    def test_since_that_is_no_version_and_the_removed_days_are_refused(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        for args in (("--since", "2026-11-01x"), ("--since", "last week"), ("--since", "v0.28.5"), ("--since", ""),
                     ("--days", "30")):
            self.assertEqual(self.cli(r, "report", *args).returncode, 2, args)

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
