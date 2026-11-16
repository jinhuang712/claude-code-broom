"""What kept a Stop hook running until Claude Code gave up on it at 300 seconds: a process holding a pipe, input that is
never closed, and nothing saying where the time went."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import unittest
from unittest import mock

from support import BROOM, BroomCase

from broom import hooktrace
from broom.gitutil import CLOCK, run, run_bytes
from broom.hooktrace import descendants

# A tool that finishes and leaves a daemon, in a session of its own, holding the tool's stdout and stderr.
LEAVES_A_DAEMON = ("import subprocess; subprocess.Popen(['sleep', '12'], start_new_session=True); print('findings')")


class HangTests(BroomCase):
    def tearDown(self) -> None:
        CLOCK.end, CLOCK.env = None, {}
        super().tearDown()

    def test_a_tool_that_left_a_daemon_behind_is_not_waited_for(self) -> None:
        start = time.monotonic()
        rc, out, _ = run([sys.executable, "-c", LEAVES_A_DAEMON], self.tmp, timeout=60)
        self.assertEqual((rc, out.strip()), (0, "findings"))
        self.assertLess(time.monotonic() - start, 3, "it took 12 s, the daemon's life, with pipes")

    def test_a_tool_cut_off_at_the_timeout_is_not_waited_for_either(self) -> None:
        start = time.monotonic()
        rc, _, _ = run([sys.executable, "-c", LEAVES_A_DAEMON.replace("print('findings')", "import time; time.sleep(30)")],
                       self.tmp, timeout=0.5)
        self.assertIsNone(rc)
        self.assertLess(time.monotonic() - start, 4)

    def test_a_tool_that_reads_its_input_gets_none_and_does_not_wait_for_it(self) -> None:
        start = time.monotonic()
        rc, out, _ = run(["cat"], self.tmp, timeout=30)
        self.assertEqual((rc, out), (0, ""))
        self.assertLess(time.monotonic() - start, 3)

    def test_what_a_tool_writes_comes_back_whole_and_stdin_can_be_given(self) -> None:
        rc, out, err = run_bytes([sys.executable, "-c",
                                  "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read() * 50000);"
                                  "sys.stderr.write('e')"], self.tmp, timeout=30, stdin=b"abc")
        self.assertEqual((rc, len(out), err), (0, 150000, b"e"), "more than a pipe holds, and bytes as written")

    def test_git_is_told_not_to_start_a_file_monitor_prompt_or_lock_the_index(self) -> None:
        rc, out, _ = run(["sh", "-c", "echo $GIT_OPTIONAL_LOCKS $GIT_TERMINAL_PROMPT $GIT_CONFIG_KEY_0=$GIT_CONFIG_VALUE_0"],
                         self.tmp)
        self.assertEqual(out.strip(), "0 0 core.fsmonitor=false")
        with mock.patch.dict("os.environ", {"GIT_CONFIG_COUNT": "2"}):  # the person's own config is left alone
            _, out, _ = run(["sh", "-c", "echo $GIT_CONFIG_COUNT-$GIT_CONFIG_KEY_0"], self.tmp)
        self.assertEqual(out.strip(), "2-")

    def held_open(self, event: str, payload: dict) -> float:
        """How long a hook takes to end when its input arrives whole and the pipe is never closed."""
        p = subprocess.Popen([str(BROOM), "hook", event], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=self.env)
        assert p.stdin is not None
        p.stdin.write(json.dumps(payload).encode())
        p.stdin.flush()  # the pipe stays open, as when the harness doesn't close it
        start = time.monotonic()
        try:
            rc = p.wait(timeout=20)
        finally:
            p.kill()
            p.communicate()
        self.assertEqual(rc, 0)
        return time.monotonic() - start

    def test_a_hook_whose_input_is_never_closed_still_runs(self) -> None:
        repo = self.repo({"a.py": "x = 1\n"})
        took = self.held_open("prompt", {"session_id": "s1", "cwd": str(repo), "hook_event_name": "UserPromptSubmit"})
        self.assertLess(took, 8, "it didn't wait for an end of input that never comes")

    def test_the_commit_hook_does_not_wait_for_an_end_of_input_either(self) -> None:
        repo = self.repo({"a.py": "x = 1\n"})
        took = self.held_open("commit", {"session_id": "s1", "cwd": str(repo), "hook_event_name": "PreToolUse",
                                         "tool_name": "Bash", "tool_input": {"command": "git commit -m x"},
                                         "tool_use_id": "t1"})
        self.assertLess(took, 8)


class TraceTests(BroomCase):
    def test_a_hook_still_running_leaves_where_it_was_and_what_it_had_started(self) -> None:
        child = subprocess.Popen(["sleep", "5"])
        self.addCleanup(lambda: (child.kill(), child.wait()))
        with mock.patch.object(hooktrace, "SLOW_AFTER", 0.2):
            hooktrace.watch("stop", str(self.tmp))
            time.sleep(1.2)
        text = hooktrace.LOG.read_text()
        self.assertIn("hook stop", text)
        self.assertIn("still running", text)
        self.assertIn("Thread", text, "where each thread is")
        self.assertIn("sleep 5", text, "the process it had started")

    def test_a_hook_that_ends_in_time_writes_nothing(self) -> None:
        hooktrace.watch("stop", str(self.tmp))  # SLOW_AFTER is 20 s: the test is over long before
        self.assertFalse(hooktrace.LOG.exists())

    def test_descendants_are_the_processes_below_one_however_far(self) -> None:
        rows = ["10 1 01:00 hook", "11 10 00:30 tsc", "12 11 00:20 tsserver", "13 1 05:00 other", "14 13 00:01 node"]
        self.assertEqual(descendants(rows, 10), ["11 10 00:30 tsc", "12 11 00:20 tsserver"])


if __name__ == "__main__":
    unittest.main()
