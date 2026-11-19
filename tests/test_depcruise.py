"""The dependency-cruiser broom picks for cycles between folders in TS/JS: which TypeScript sits beside a copy. The
doctor's side of the pick is in test_doctor and test_protection, and the scan's in test_foldercycles."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from support import BroomCase

from broom.depcruise import typescript_beside


class TypescriptBesideTests(BroomCase):
    def exe(self, typescript: str = None, *, own: bool = False) -> str:
        return self.npm_depcruise(self.fake_path(), typescript, own=own)["PATH"] + "/depcruise"

    def test_the_typescript_node_would_load_is_read_from_the_folders_it_searches_in_order(self) -> None:
        self.assertEqual(typescript_beside(self.exe("7.0.2")), "7.0.2", "beside the package, by the real path")
        own = self.exe("5.9.3", own=True)
        modules = Path(os.path.realpath(own)).parents[2]  # the node_modules that holds the package
        (modules / "typescript").mkdir()
        (modules / "typescript" / "package.json").write_text('{"version": "7.0.2"}')
        self.assertEqual(typescript_beside(own), "5.9.3", "the package's own node_modules comes first")
        self.assertIsNone(typescript_beside(self.exe()))


if __name__ == "__main__":
    unittest.main()
