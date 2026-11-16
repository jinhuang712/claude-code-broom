"""The ledger: a line for every block, fix, pass and skip, the turn summary the user sees, and `broom report`."""

from __future__ import annotations

import json
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from support import BROOM, HAS_PY, BroomCase, py_function

from broom import checks, ledger

DAY = 86400
QUIET = '{"smells_off": ["dead_code"]}'  # a function nothing calls is dead code too: not what these tests are about


def lines(event: str = "") -> list:
    return [r for r in ledger.read(ledger.LEDGER) if not event or r["event"] == event]


class LedgerCase(BroomCase):
    def repo(self, files: dict) -> Path:
        return super().repo({".broom.json": QUIET, **files})

    def huge(self, r: Path, name: str = "a.py") -> None:
        """A function past the hard limit, staged: it blocks a commit, and never passes on a retry."""
        (r / name).write_text(py_function("huge", 120))
        self.sh(r, "git", "add", name)

    def stop(self, r: Path, session: str = "s1") -> dict:
        return self.hook("stop", {"session_id": session, "cwd": str(r), "permission_mode": "default"})

    def edit(self, r: Path, name: str, session: str = "s1") -> None:
        self.hook("edit", {"session_id": session, "cwd": str(r), "tool_name": "Edit",
                           "tool_input": {"file_path": str(r / name)}})


class RecordTest(LedgerCase):
    def test_a_block_and_then_a_fix_leave_a_line_each(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        self.assertIn("huge is 120 lines long", self.denied(self.commit(r, "git commit -m x")))
        (block,) = lines("block")
        self.assertEqual((block["repo"], block["where"], block["tool"], block["rule"], block["file"]),
                         (str(r), "commit", "smells", "function_lines", "a.py"))
        self.assertEqual(lines("fix"), [], "nothing is fixed yet")
        (r / "a.py").write_text(py_function("small", 20))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        (fix,) = lines("fix")
        self.assertEqual((fix["key"], fix["rule"], fix["where"]), (block["key"], "function_lines", "commit"))

    def test_a_finding_that_only_changed_isnt_fixed(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        (r / "a.py").write_text(py_function("huge", 110))  # shorter, and still past the hard limit: another message
        self.sh(r, "git", "add", "a.py")
        self.assertIn("huge is 110 lines long", self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(len(lines("block")), 2)
        self.assertEqual(lines("fix"), [], "the same finding, not a fixed one")
        (r / "a.py").write_text(py_function("small", 20))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual([x["key"] for x in lines("fix")], [lines("block")[1]["key"]], "fixed under its last key")

    def test_a_commit_of_other_files_fixes_nothing(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.huge(r)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        (r / "b.py").write_text("y = 2\n")
        self.sh(r, "git", "add", "b.py")
        self.sh(r, "git", "restore", "--staged", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(lines("fix"), [], "a.py wasn't checked: its finding stays open")

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_a_retry_passes_a_lint_finding_and_the_ledger_says_how(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("import os\n")
        self.sh(r, "git", "add", "a.py")
        self.assertIn("F401", self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        self.assertEqual([(x["rule"], x["tool"]) for x in lines("block")], [("F401", "ruff")])
        (through,) = lines("pass")
        self.assertEqual((through["how"], through["key"]), ("retry", lines("block")[0]["key"]))
        self.assertEqual(self.stop(r)["systemMessage"], "broom let 1 through this turn: 1 F401 (retry)")

    def test_accepting_with_a_reason_is_a_pass_with_the_reason(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.cli(r, "known", "--accept", "legacy code").returncode, 0)
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        (through,) = lines("pass")
        self.assertEqual((through["how"], through["why"], through["where"]), ("accept", "legacy code", "commit"))
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom let 1 through this turn: 1 function_lines (accepted: legacy code)")
        self.assertEqual(self.stop(r), {}, "the turn is over: its summary is said once")

    def test_stopping_again_ends_the_turn_and_the_ledger_and_the_summary_say_what_was_left(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        (r / "a.py").write_text(py_function("medium", 60))  # past the soft limit: a hint, which stops a turn once
        (r / "b.py").write_text(py_function("huge", 120).replace("+=", "-="))  # not a copy of a.py's
        for name in ("a.py", "b.py"):
            self.edit(r, name)
        self.assertIn("issue(s) in this turn's changes", self.stop(r)["reason"])
        self.assertEqual(sorted((x["file"], x["where"]) for x in lines("block")), [("a.py", "stop"), ("b.py", "stop")])
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom let 2 through this turn: 1 function_lines (stop-again), "
                         "1 function_lines (turn-ended); 2 issue(s) left unfixed")
        self.assertEqual(sorted((x["file"], x["how"]) for x in lines("pass")),
                         [("a.py", "stop-again"), ("b.py", "turn-ended")])

    def test_a_finding_fixed_during_the_turn_is_a_fix_at_the_stop(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.edit(r, "a.py")
        self.assertIn("huge is 120", self.stop(r)["reason"])
        (r / "a.py").write_text(py_function("small", 20))
        self.edit(r, "a.py")
        self.assertNotIn("decision", self.stop(r))
        (block,), (fix,) = lines("block"), lines("fix")
        self.assertEqual((fix["key"], fix["where"]), (block["key"], "stop"))

    def test_a_hint_at_a_commit_is_noted_and_blocks_nothing(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("medium", 60))
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        self.assertEqual([(x["rule"], x["file"]) for x in lines("hint")], [("function_lines", "a.py")])
        self.assertEqual(lines("block"), [])

    def test_a_tool_that_didnt_run_leaves_a_skip_and_a_fix_waits_for_it(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.env = self.fake_path()  # no ruff
        (r / "a.py").write_text("y = 1\n")
        self.sh(r, "git", "add", "a.py")
        self.commit(r, "git commit -m x")
        (skip,) = [x for x in lines("skip") if x["tool"] == "ruff"]
        self.assertEqual(skip["note"], "missing:ruff (brew install ruff)")
        self.commit(r, "git commit -m y")
        self.assertEqual(len([x for x in lines("skip") if x["tool"] == "ruff"]), 1, "recorded once per session")
        entry = {"file": str(r / "a.py"), "tool": "ruff", "rule": "F401"}
        for files, notes in (([r / "a.py"], [skip["note"]]), ([r / "b.py"], []), ([r / "a.py"], ["timeout:ruff in x"])):
            ledger.fixes({"k": entry}, {}, set(), files, notes)
            self.assertEqual(lines("fix"), [], (files, notes))
        ledger.fixes({"k": entry}, {}, {"k"}, [r / "a.py"], [])
        self.assertEqual(lines("fix"), [], "accepted since: not fixed")
        ledger.fixes({"k": entry}, {}, set(), [r / "a.py"], ["missing:golangci-lint (brew install golangci-lint)"])
        self.assertEqual([x["key"] for x in lines("fix")], ["k"], "a note about another tool holds nothing back")

    def test_a_smell_waits_for_the_tool_that_measures_it(self) -> None:
        py, go = {"file": "a.py", "tool": "smells", "rule": "magic_numbers"}, {"file": "a.go", "tool": "smells"}
        size = {"file": "a.py", "tool": "smells", "rule": "function_lines"}
        self.assertTrue(ledger.covers("missing:ruff (brew install ruff)", py))
        self.assertFalse(ledger.covers("missing:ruff (brew install ruff)", size), "Python's own parser measures it")
        self.assertFalse(ledger.covers("missing:ruff (brew install ruff)", go))
        self.assertTrue(ledger.covers("timeout:ruff measuring smells", size))
        self.assertTrue(ledger.covers("missing:golangci-lint (brew install golangci-lint)", go))

    def test_the_time_of_each_check_is_noted_for_a_hook_and_not_otherwise(self) -> None:
        tool = ("ruff:/x", lambda: ([], []))
        with mock.patch.object(checks, "plan", return_value=[tool]):
            checks.run_checks([Path("a.py")])
            self.assertEqual(lines("time"), [])
            checks.run_checks([Path("a.py")], self.tmp / "slow.json")
        (took,) = lines("time")
        self.assertEqual((took["check"], took["repo"]), ("ruff", "/x"))
        self.assertEqual(took["seconds"], round(took["seconds"], 2))

    def test_a_hook_that_failed_leaves_an_error_line_and_lets_the_action_through(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        bad = {"session_id": "s1", "cwd": str(r), "tool_name": "Edit", "tool_input": "not an object"}
        out = subprocess.run([str(BROOM), "hook", "edit"], input=json.dumps(bad), capture_output=True, text=True,
                             env=self.env, cwd=r)
        self.assertEqual((out.returncode, out.stdout), (0, ""))
        (error,) = lines("error")
        self.assertEqual((error["where"], error["repo"]), ("edit", str(r)))
        self.assertIn("AttributeError", error["note"])

    def test_the_turn_summary_groups_what_was_let_through(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        turn = self.tmp / "turn"
        turn.mkdir()
        magic = {str(n): {"file": str(r / "a.py"), "tool": "smells", "rule": "magic_numbers"} for n in range(2)}
        ledger.let_through(magic, "retry", turn)
        ledger.let_through({"k": {"file": str(r / "a.py"), "tool": "smells", "rule": "function_lines"}}, "accept", turn,
                           why="legacy")
        self.assertEqual(ledger.through_line(turn),
                         "broom let 3 through this turn: 2 magic_numbers (retry), 1 function_lines (accepted: legacy)")
        ledger.forget_through(turn)
        self.assertEqual(ledger.through_line(turn), "", "a turn that let nothing through says nothing")

    def test_a_turn_no_stop_hook_ended_doesnt_leak_its_summary_into_the_next(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.cli(r, "known", "--accept", "legacy code")
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})
        self.assertEqual(self.stop(r), {}, "the new prompt started a turn that let nothing through")

    def test_the_ledger_stays_bounded_and_a_ledger_that_cant_be_written_stops_nothing(self) -> None:
        old, now = time.time() - 100 * DAY, time.time()
        pad = "k" * 40
        rows = [{"t": t, "repo": "/a", "event": "block", "key": pad} for t in (old, now)]
        ledger.LEDGER.parent.mkdir(parents=True, exist_ok=True)
        ledger.LEDGER.write_text("".join(json.dumps(x) + "\n" for x in rows))
        with mock.patch.object(ledger, "MAX_BYTES", 300):
            ledger.write([{"t": now, "repo": "/a", "event": "fix", "key": pad}])
        self.assertEqual([x["event"] for x in lines()], ["block", "fix"], "the line older than 90 days is gone")
        with mock.patch.object(ledger, "MAX_BYTES", 1000):
            ledger.write([{"t": now, "repo": "/a", "event": "pass", "key": str(n)} for n in range(50)])
        self.assertLess(ledger.LEDGER.stat().st_size, 1000, "recent lines go too, the oldest first, when it is over")
        self.assertEqual(lines()[-1]["key"], "49")
        blocker = self.tmp / "file"
        blocker.write_text("")
        with mock.patch.object(ledger, "LEDGER", blocker / "ledger.jsonl"):
            ledger.write([{"t": now, "repo": "/a", "event": "fix"}])  # its directory is a file: no error


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
        self.assertEqual((every["repos"], every["blocked"]), ("all", 5), "the other repo's too")

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
