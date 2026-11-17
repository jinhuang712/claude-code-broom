"""The hooks at a session's start: quiet where a repo lacks nothing, and silent outside a repo."""

from __future__ import annotations

import time
import unittest

from support import HAS_GOPLS, BroomCase


class SessionHooksTest(BroomCase):
    @unittest.skipUnless(HAS_GOPLS, "go tools missing")
    def test_session_is_quiet_and_fast_when_healthy(self) -> None:
        r = self.go_repo()
        env = {**self.env, "CLAUDE_CONFIG_DIR": str(self.config_dir())}
        self.cli(r, "install-hook", env=env)  # git's hook is a gap like any tool
        self.assertEqual(self.noted(self.session(r, "a", env)), "")
        start = time.time()
        self.assertEqual(self.noted(self.session(r, "b", env)), "")
        self.assertLess(time.time() - start, 1.0, "the cached doctor keeps SessionStart fast")
        self.assertEqual(self.session(self.repo({"README.md": "hi\n"}), "c", env), {}, "no languages, nothing to say")

    def test_a_folder_that_is_no_repo_is_told_nothing(self) -> None:
        folder = self.tmp / "plain"
        folder.mkdir()
        (folder / "a.py").write_text("x = 1\n")
        self.assertEqual(self.session(folder, "n1", self.env), {})
        self.assertEqual(self.session(folder, "n1", self.env, event="session-scan"), {})


if __name__ == "__main__":
    unittest.main()
