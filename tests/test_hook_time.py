"""One run of a hook takes at most 30 seconds, whatever the tools it runs are doing."""

from __future__ import annotations

import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from support import BROOM, ROOT, BroomCase

from broom import checks, hotspots
from broom.gitutil import CLOCK, HOOK_SECONDS, THREAD_VARS, run

CLAUDE_CODE_KILLS_AT = 30  # seconds: the `timeout` of every hook in hooks.json


class HookTimeTests(BroomCase):
    def tearDown(self) -> None:
        CLOCK.end, CLOCK.env = None, {}
        super().tearDown()

    def test_every_hook_ends_before_claude_code_ends_it(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        seen = [h for groups in hooks.values() for g in groups for h in g["hooks"]]
        self.assertGreaterEqual(len(seen), 7)
        for h in seen:  # async ones too: they hold the CPU while Claude works
            self.assertEqual(h.get("timeout"), CLAUDE_CODE_KILLS_AT, h)
        self.assertLess(HOOK_SECONDS + 3, CLAUDE_CODE_KILLS_AT)  # the hook gives up on its own first

    def test_a_command_is_cut_off_with_everything_it_started(self) -> None:
        CLOCK.start(0.3)
        marker = self.tmp / "marker"
        start = time.monotonic()
        rc, _, _ = run(["sh", "-c", f"(sleep 1; touch {marker}) & wait"], self.tmp, timeout=60)
        self.assertIsNone(rc)
        self.assertLess(time.monotonic() - start, 1.0)
        time.sleep(1.4)
        self.assertFalse(marker.exists(), "the command's child outlived the hook's time")

    def test_nothing_starts_once_the_time_is_used_up(self) -> None:
        CLOCK.start(0)
        marker = self.tmp / "marker"
        self.assertEqual(run(["touch", str(marker)], self.tmp), (None, "", ""))
        self.assertFalse(marker.exists())

    def test_a_hook_keeps_each_tool_to_a_few_threads_unless_the_person_set_them(self) -> None:
        environ = mock.patch.dict(os.environ)
        environ.start()
        self.addCleanup(environ.stop)
        for name in THREAD_VARS:
            os.environ.pop(name, None)
        show = ["sh", "-c", "echo $GOMAXPROCS-$RAYON_NUM_THREADS-$CARGO_BUILD_JOBS"]
        self.assertEqual(run(show, self.tmp)[1].strip(), "--", "outside a hook, every core")
        CLOCK.start(30)
        threads = str(max(2, (os.cpu_count() or 4) // 4))
        self.assertEqual(run(show, self.tmp)[1].strip(), f"{threads}-{threads}-{threads}")
        with mock.patch.dict(os.environ, {"GOMAXPROCS": "7"}):
            CLOCK.start(30)
            self.assertEqual(run(show, self.tmp)[1].strip(), f"7-{threads}-{threads}")

    def test_outside_a_hook_a_command_keeps_its_own_timeout(self) -> None:
        self.assertIsNone(CLOCK.left())
        self.assertEqual(run(["true"], self.tmp)[0], 0)
        self.assertIsNone(run(["sleep", "5"], self.tmp, timeout=0.2)[0])

    def test_a_commit_check_stuck_in_a_tool_ends_at_the_hook_limit(self) -> None:
        repo = self.repo({"a.py": "x = 1\n"})
        (repo / "a.py").write_text("x = 2\n")
        self.sh(repo, "git", "add", "-A")
        env = {**self.fake_path(keep=("sleep",), fakes={"ruff": "sleep 60"}), "BROOM_HOOK_SECONDS": "2"}
        payload = {"session_id": "s1", "cwd": str(repo), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "git commit -m x"}, "tool_use_id": "t1"}
        start = time.monotonic()
        r = subprocess.run([str(BROOM), "hook", "commit"], input=json.dumps(payload), capture_output=True,
                           text=True, env=env, cwd=repo)
        self.assertLess(time.monotonic() - start, 15)  # the tool would have taken 60
        self.assertEqual((r.returncode, r.stderr.strip()), (0, ""))
        self.assertEqual(self.denied(json.loads(r.stdout) if r.stdout.strip() else {}), "")  # late is not wrong

    def test_a_check_cut_short_is_late_not_slow(self) -> None:
        slow_path = self.tmp / "slow.json"
        quick = ("late", lambda: ([], ["timeout:ruff in /x"]))
        with mock.patch.object(checks, "plan", return_value=[quick]):
            checks.run_checks([Path("a.py")], slow_path)
            self.assertFalse(slow_path.exists(), "cut short after a moment: late, not slow")
            with mock.patch.object(checks, "SLOW_SECONDS", 0):
                checks.run_checks([Path("a.py")], slow_path)
        self.assertEqual(list(json.loads(slow_path.read_text())), ["late"])

    def test_a_slow_check_is_skipped_for_a_while_in_every_session_and_says_so(self) -> None:
        slow_path = self.tmp / "slow.json"
        calls = []
        slow = ("late", lambda: (calls.append(1), ([], ["timeout:ruff in /x"]))[1])
        with mock.patch.object(checks, "plan", return_value=[slow]), mock.patch.object(checks, "SLOW_SECONDS", 0):
            checks.run_checks([Path("a.py")], slow_path)
            _issues, notes = checks.run_checks([Path("a.py")], slow_path)
            self.assertEqual(len(calls), 1, "the second try didn't run it")
            self.assertTrue(any(n.startswith("timeout:late skipped for now") for n in notes), notes)
            slow_path.write_text(json.dumps({"late": time.time() - checks.SLOW_KEEP - 1}))
            checks.run_checks([Path("a.py")], slow_path)
        self.assertEqual(len(calls), 2, "after SLOW_KEEP it gets another go")

    def test_a_scan_that_ran_out_of_time_is_scanned_again(self) -> None:
        repo = self.repo({"a.py": "x = 1\n"})
        scans = []

        def scan(*_args, **_kw):
            scans.append(1)
            return [], (["timeout:ruff measuring smells"] if len(scans) == 1 else [])

        with mock.patch.object(hotspots, "find_smells", scan):
            first = hotspots.summary(repo)
            self.assertTrue(first["partial"])
            self.assertEqual(hotspots.summary(repo)["partial"], False)  # not served from the partial one
            self.assertEqual(len(scans), 2)
            hotspots.summary(repo)
            self.assertEqual(len(scans), 2)  # a whole scan is cached for its commit

    def test_the_note_of_a_partial_scan_says_it_is_a_floor(self) -> None:
        data = {"head": "h", "total": 9, "severe": 4, "hotspots": ["a.py"], "partial": True}
        self.assertIn("at least 4 code smell", hotspots.session_note(self.tmp, data))
        self.assertNotIn("at least", hotspots.session_note(self.tmp, {**data, "partial": False}))


if __name__ == "__main__":
    unittest.main()
