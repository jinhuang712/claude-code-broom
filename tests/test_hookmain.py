"""`broom hook <event>`: the way in for Claude Code's hooks, which never lets a broken input stop the work."""

from __future__ import annotations

import subprocess
import unittest

from support import BROOM, BroomCase


class HookMainTest(BroomCase):
    def raw(self, event: str, text: str) -> subprocess.CompletedProcess:
        r = self.repo({"a.py": "x = 1\n"})
        return subprocess.run([str(BROOM), "hook", event], input=text, capture_output=True, text=True, env=self.env,
                              cwd=r)

    def test_input_that_is_no_json_object_does_nothing_and_stops_nothing(self) -> None:
        for event in ("edit", "stop", "prompt", "commit"):
            for text in ("", "not json", "[1, 2]"):
                out = self.raw(event, text)
                self.assertEqual((out.returncode, out.stdout), (0, ""), f"{event}: {text!r} {out.stderr}")

    def test_an_event_nobody_handles_is_refused(self) -> None:
        out = self.raw("nonsense", "{}")
        self.assertEqual(out.returncode, 2)
        self.assertIn("invalid choice", out.stderr)


if __name__ == "__main__":
    unittest.main()
