"""The tests never write into the user's own data directory: the run has a directory of its own, each test has one
on top of it, and a write that still reaches the user's is refused and fails the test that tried it."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import isolation
from isolation import BROOM, DEFAULT_DATA, RealDataWrite
from support import BroomCase

from broom import hooktrace, ledger, state

OPEN_NEW = os.O_WRONLY | os.O_CREAT | os.O_TRUNC


class IsolationTests(BroomCase):
    def refused(self, event: str, *args) -> bool:
        """Whether the guard refuses `event`, and has the record the test would fail on; the record is taken."""
        try:
            isolation.audit(event, args)
        except RealDataWrite:
            return bool(isolation.take_violations())
        self.assertEqual(isolation.take_violations(), [], f"{event} is allowed and left a record")
        return False

    def test_the_run_and_every_test_keep_their_data_in_a_directory_of_their_own(self) -> None:
        self.assertEqual(os.environ["CLAUDE_PLUGIN_DATA"], str(isolation.DATA))
        self.assertFalse(isolation.reaches_real(isolation.DATA))
        self.assertEqual(state.DATA_ROOT, self.tmp / "data", "the test's, over the run's")
        self.assertEqual((ledger.LEDGER, hooktrace.LOG), (self.tmp / "data" / "ledger.jsonl",
                                                          self.tmp / "data" / "hook-trace.log"))

    def test_no_module_keeps_a_path_into_the_real_directory(self) -> None:
        self.assertGreater(len(isolation.PATHS), 10, "the paths broom derives from its data directory are found")
        for module, attr, rel in isolation.PATHS:
            self.assertEqual(getattr(module, attr), self.tmp / "data" / rel, f"{module.__name__}.{attr}")
        for name, module in sys.modules.items():
            if name == "broom" or name.startswith("broom."):
                for attr, value in vars(module).items():
                    self.assertFalse(isolation.reaches_real(value) if isinstance(value, Path) else False,
                                     f"{name}.{attr}")

    def test_a_write_into_the_real_directory_is_refused_and_recorded(self) -> None:
        target = str(DEFAULT_DATA / "x")
        self.assertTrue(self.refused("open", target, "w", OPEN_NEW))
        self.assertTrue(self.refused("open", target, "r+", os.O_RDWR))
        self.assertTrue(self.refused("open", Path(DEFAULT_DATA, "x"), "a", os.O_WRONLY | os.O_APPEND))
        self.assertTrue(self.refused("os.mkdir", str(DEFAULT_DATA / "d"), 0o777, None))
        self.assertTrue(self.refused("os.remove", target, None))
        self.assertTrue(self.refused("os.rename", str(self.tmp / "a"), target, None, None), "moved in")
        self.assertTrue(self.refused("os.rename", target, str(self.tmp / "a"), None, None), "moved out")
        self.assertTrue(self.refused("os.symlink", str(self.tmp), target, None))
        self.assertTrue(self.refused("shutil.rmtree", str(DEFAULT_DATA), None))
        self.assertTrue(self.refused("os.utime", target, None, None, None, None))

    def test_a_read_or_a_write_elsewhere_is_left_alone(self) -> None:
        target = str(DEFAULT_DATA / "x")
        self.assertFalse(self.refused("open", target, "r", os.O_RDONLY))
        self.assertFalse(self.refused("open", 7, "w", OPEN_NEW), "a file descriptor")
        self.assertFalse(self.refused("open", str(self.tmp / "x"), "w", OPEN_NEW))
        self.assertFalse(self.refused("open", str(DEFAULT_DATA) + "-other/x", "w", OPEN_NEW), "a sibling of it")
        self.assertFalse(self.refused("os.mkdir", str(self.tmp / "d"), 0o777, None))
        self.assertFalse(self.refused("os.symlink", target, str(self.tmp / "link"), None), "a link to it")

    def test_a_broom_started_without_a_data_directory_of_its_own_is_refused(self) -> None:
        argv = [str(BROOM), "hook", "stop"]
        self.assertTrue(self.refused("subprocess.Popen", str(BROOM), argv, None, {"PATH": "/usr/bin"}))
        self.assertTrue(self.refused("subprocess.Popen", str(BROOM), argv, None,
                                     {"CLAUDE_PLUGIN_DATA": str(DEFAULT_DATA)}))
        self.assertFalse(self.refused("subprocess.Popen", str(BROOM), argv, None, self.env))
        self.assertFalse(self.refused("subprocess.Popen", str(BROOM), argv, None, None), "it inherits the run's")
        self.assertFalse(self.refused("subprocess.Popen", "git", ["git", "status"], None, {"PATH": "/usr/bin"}))

    def test_the_guard_is_installed_and_stops_a_write_before_it_happens(self) -> None:
        protected = self.tmp / "protected"
        with mock.patch.object(isolation, "REAL_ROOTS", (str(protected),)):
            with self.assertRaises(RealDataWrite):
                (protected / "ledger.jsonl").write_text("x")
            with self.assertRaises(RealDataWrite):
                protected.mkdir()
        self.assertFalse(protected.exists())
        self.assertEqual(len(isolation.take_violations()), 2, "what a test fails on in its teardown")


if __name__ == "__main__":
    unittest.main()
