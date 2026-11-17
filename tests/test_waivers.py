"""Self-waivers: a loosened .broom.json, a new lint suppression and a `git commit --no-verify` are recorded and shown,
never blocked."""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

from support import HAS_PY, py_function

from broom import ledger, waivers
from test_ledger import LedgerCase, lines

# Written in two pieces: this file would otherwise hold suppressions itself.
NOQA = "# no" + "qa: E501"
TYPE_IGNORE = "# type" + ": ignore[assignment]"


class SuppressionTest(LedgerCase):
    def waived(self, kind: str = "") -> list:
        return [x for x in lines("waiver") if not kind or x["kind"] == kind]

    def test_what_counts_as_a_suppression(self) -> None:
        yes = [f"x = 1  {NOQA}", f"x = 1  {TYPE_IGNORE}", "// eslint" + "-disable-next-line no-console",
               "/* style" + "lint-disable */", "//no" + "lint:errcheck", "// @ts" + "-ignore",
               "#[al" + "low(dead_code)]", "// biome" + "-ignore lint/x: why",
               "// swift" + "lint:disable:next force_cast", "// oxlint" + "-disable"]
        for text in yes:
            self.assertTrue(waivers.suppression_in(text), text)
        for text in ("x = 1", 'text = "no' + 'qa"', "# a comment", "// plain"):
            self.assertIsNone(waivers.suppression_in(text), text)

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_a_suppression_the_change_adds_is_recorded_and_one_it_didnt_add_is_not(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(f"x = 1  {NOQA}\n")
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "", "a waiver blocks nothing")
        (waiver,) = self.waived()
        self.assertEqual((waiver["kind"], waiver["file"], waiver["note"], waiver["where"], waiver["repo"]),
                         ("suppression", "a.py", "no" + "qa", "commit", str(r)))
        self.assertEqual(self.stop(r)["systemMessage"], "broom saw 1 self-waiver this turn: suppression in a.py")
        self.assertEqual(self.stop(r), {}, "said once")
        self.sh(r, "git", "commit", "-qm", "x")
        (r / "a.py").write_text(f"x = 1  {NOQA}\ny = 2\n")  # the old line is no change of this commit
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.denied(self.commit(r, "git commit -m y")), "")
        self.assertEqual(len(self.waived()), 1)

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_the_same_waiver_seen_again_in_the_turn_counts_once(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(f"x = 1  {NOQA}\n" + py_function("huge", 120))  # blocked, so checked again
        self.sh(r, "git", "add", "a.py")
        for _ in range(3):
            self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(len(self.waived("suppression")), 1)
        (r / "a.py").write_text(f"x = 1  {NOQA}\ny = 2  {NOQA}\n" + py_function("huge", 120))
        self.sh(r, "git", "add", "a.py")
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(len(self.waived("suppression")), 2, "another line is another waiver")
        self.assertEqual(self.stop(r)["systemMessage"], "broom saw 2 self-waivers this turn: suppression in a.py x2")

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_the_turn_end_sees_a_suppression_too(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(f"x = 1  {TYPE_IGNORE}\n")
        self.edit(r, "a.py")
        out = self.stop(r)
        self.assertNotIn("decision", out)
        self.assertEqual(out["systemMessage"], "broom saw 1 self-waiver this turn: suppression in a.py")
        (waiver,) = self.waived()
        self.assertEqual((waiver["where"], waiver["note"]), ("stop", "type" + ": ignore"))

    def test_a_commit_with_no_verify_is_a_waiver(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("x = 2\n")
        self.sh(r, "git", "add", "a.py")
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        self.assertEqual(self.waived(), [], "a commit that is checked loosens nothing")
        self.assertEqual(self.commit(r, "git commit --dry-run --no-verify -m x"), {})
        self.assertEqual(self.waived(), [], "nothing is committed")
        self.assertEqual(self.commit(r, "git commit --no-verify -m x"), {})
        (waiver,) = self.waived()
        self.assertEqual((waiver["kind"], waiver["note"], waiver["repo"], "file" in waiver),
                         ("no-verify", "git commit --no-verify", str(r), False))
        self.assertEqual(self.stop(r)["systemMessage"], "broom saw 1 self-waiver this turn: no-verify")


class ConfigTest(LedgerCase):
    def test_a_looser_bar_is_a_waiver_and_a_tighter_one_is_not(self) -> None:
        loose = [  # (before, after, what it says)
            ({}, {"smells_off": ["magic_numbers", "todo"]}, ["smells_off +magic_numbers +todo"]),
            ({"smells_off": ["todo"]}, {"smells_off": ["todo", "globals"]}, ["smells_off +globals"]),
            ({"exclude": ["a/*"]}, {"exclude": ["a/*", "vendor/**"]}, ["exclude +vendor/**"]),
            ({}, {"legacy": ["old/*"]}, ["legacy +old/*"]),
            ({}, {"limits": {"function_lines": [80, 150]}}, ["limits function_lines 50/100 -> 80/150"]),
            ({"limits": {"params": [5, 8]}}, {"limits": {"params": [5, 9]}}, ["limits params 5/8 -> 5/9"]),
            ({}, {"test_limits": {"file_lines": [800, 2000]}}, ["test_limits file_lines 400/1000 -> 800/2000"]),
            ({}, {"check_on": "off"}, ["check_on off"]),
            ({"smells": "on"}, {"smells": "off"}, ["smells off"]),
        ]
        for before, after, notes in loose:
            self.assertEqual(waivers.loosened(before, after), notes, after)
        tight = [
            ({"smells_off": ["todo", "globals"]}, {"smells_off": ["todo"]}),
            ({"exclude": ["a/*", "b/*"]}, {"exclude": ["a/*"]}),
            ({"limits": {"function_lines": [80, 150]}}, {"limits": {"function_lines": [60, 100]}}),
            ({"limits": {"function_lines": [80, 150]}}, {}),
            ({"check_on": "off"}, {"check_on": "stop"}),
            ({"check_on": "off"}, {"check_on": "off"}),
            ({}, {"limits": {"function_lines": [50, 100]}}),
            ({}, {"format_on": "off", "format_scope": "file"}),
        ]
        for before, after in tight:
            self.assertEqual(waivers.loosened(before, after), [], after)

    def test_a_test_limit_is_compared_with_the_limit_the_tests_had(self) -> None:
        before = {"limits": {"file_lines": [800, 2000]}}
        self.assertEqual(waivers.loosened(before, {**before, "test_limits": {"file_lines": [800, 2000]}}), [])
        self.assertEqual(waivers.loosened(before, {**before, "test_limits": {"file_lines": [800, 2500]}}),
                         ["test_limits file_lines 800/2000 -> 800/2500"])

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_a_commit_that_loosens_the_config_says_so_and_one_that_tightens_it_doesnt(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text("x = 2\n")
        (r / ".broom.json").write_text('{"smells_off": ["dead_code", "magic_numbers"]}')
        self.sh(r, "git", "add", "-A")
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "", "a waiver blocks nothing")
        (waiver,) = lines("waiver")
        self.assertEqual((waiver["kind"], waiver["file"], waiver["note"]),
                         ("config", ".broom.json", "smells_off +magic_numbers"))
        self.assertEqual(self.stop(r)["systemMessage"],
                         "broom saw 1 self-waiver this turn: .broom.json smells_off +magic_numbers")
        self.sh(r, "git", "commit", "-qm", "x")
        (r / "a.py").write_text("x = 3\n")
        (r / ".broom.json").write_text('{"smells_off": ["dead_code"]}')
        self.sh(r, "git", "add", "-A")
        self.assertEqual(self.denied(self.commit(r, "git commit -m y")), "")
        self.assertEqual(len(lines("waiver")), 1, "turning a smell back on is no waiver")

    def test_a_finding_that_a_looser_config_hides_is_not_fixed(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.huge(r)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        (r / ".broom.json").write_text('{"smells_off": ["dead_code", "function_lines"]}')
        self.sh(r, "git", "add", "-A")
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "", "the smell is off now")
        self.assertEqual([x["note"] for x in lines("waiver")], ["smells_off +function_lines"])
        self.assertEqual(lines("fix"), [], "turned off, not fixed")

    def test_editing_the_config_is_noted_at_once_even_when_it_turns_the_check_off(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / ".broom.json").write_text('{"smells_off": ["dead_code"], "check_on": "off"}')
        self.edit(r, ".broom.json")
        (waiver,) = lines("waiver")
        self.assertEqual((waiver["where"], waiver["note"]), ("edit", "check_on off"))
        self.assertEqual(self.stop(r), {}, "no stop hook checks now: on record, and not in a summary")


    def test_a_turn_that_only_loosened_the_config_still_says_so(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / ".broom.json").write_text('{"smells_off": ["dead_code", "todo"], "exclude": ["gen/*"]}')
        self.edit(r, ".broom.json")
        self.assertEqual(self.stop(r)["systemMessage"], "broom saw 2 self-waivers this turn: "
                         ".broom.json smells_off +todo, .broom.json exclude +gen/*")
        self.assertEqual(self.stop(r), {})

    def test_a_config_loosened_by_a_command_is_seen_at_the_turns_end(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        turn = {"session_id": "s1", "cwd": str(r)}
        self.hook("prompt", turn)
        (r / ".broom.json").write_text('{"smells_off": ["dead_code", "todo"]}')  # as `sed` would: no edit hook runs
        self.assertEqual(self.stop(r)["systemMessage"], "broom saw 1 self-waiver this turn: .broom.json smells_off +todo")
        (waiver,) = lines("waiver")
        self.assertEqual((waiver["where"], waiver["kind"]), ("stop", "config"))
        self.hook("prompt", turn)
        self.assertEqual(self.stop(r), {}, "the next turn left the file as it was: nothing to say")

    def test_a_config_loosened_and_committed_by_a_command_is_seen_too(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})
        (r / ".broom.json").write_text('{"smells_off": ["dead_code"], "exclude": ["gen/*"]}')
        self.sh(r, "git", "commit", "-qam", "looser")
        self.assertEqual(self.stop(r)["systemMessage"], "broom saw 1 self-waiver this turn: .broom.json exclude +gen/*")


class SummaryTest(LedgerCase):
    def test_the_summary_line_has_what_was_let_through_then_the_waivers(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        turn = self.tmp / "turn"
        turn.mkdir()
        entry = {"file": str(r / "a.py"), "tool": "smells", "rule": "magic_numbers"}
        ledger.let_through({"k": entry}, "accept", turn, why="legacy")
        found = [waivers.waiver("suppression", str(r), "a.py", "noqa", "x"),
                 waivers.waiver("config", str(r), ".broom.json", "smells_off +magic_numbers")]
        ledger.waived(found, turn)
        ledger.waived(found, turn)
        self.assertEqual(ledger.through_line(turn),
                         "broom let 1 through this turn: 1 magic_numbers (accepted: legacy); 2 self-waivers: "
                         "suppression in a.py, .broom.json smells_off +magic_numbers")
        self.assertEqual(len(lines("waiver")), 2, "written once each")
        ledger.forget_through(turn)
        self.assertEqual(ledger.through_line(turn), "")
        ledger.waived(found[:1], turn)
        self.assertEqual(ledger.through_line(turn), "broom saw 1 self-waiver this turn: suppression in a.py")


class WaiverReportTest(LedgerCase):
    def report(self, cwd: Path) -> dict:
        out = self.cli(cwd, "report", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_the_report_counts_the_waivers_by_kind_and_lists_the_config_ones(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        rows = [{"t": time.time(), "repo": str(r), "event": "waiver", "where": "commit", "kind": kind, "file": file,
                 "note": note} for kind, file, note in (
                     ("suppression", "a.py", "noqa"), ("suppression", "b.py", "noqa"),
                     ("config", ".broom.json", "smells_off +magic_numbers"),
                     ("no-verify", "", "git commit --no-verify"))]
        ledger.write(rows)
        data = self.report(r)
        self.assertEqual(data["waivers"], {"count": 4, "kinds": {"config": 1, "no-verify": 1, "suppression": 2},
                                           "config": [".broom.json smells_off +magic_numbers"]})
        text = self.cli(r, "report").stdout
        self.assertIn("Self-waivers", text)
        self.assertIn("  config 1, no-verify 1, suppression 2\n  .broom.json smells_off +magic_numbers", text)
        other = self.repo({"b.py": "y = 1\n"})
        self.assertEqual(self.report(other)["waivers"], {"count": 0, "kinds": {}, "config": []})


if __name__ == "__main__":
    unittest.main()
