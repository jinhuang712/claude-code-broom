"""The `use` graph of Rust files behind the import and folder cycles: how a path is read, and which cycles count.
Sample code is a list of lines, so that none of it stands in this file as code of its own."""

from __future__ import annotations

import unittest

from support import BroomCase

from broom.rustcycles import rust_folder_cycles, rust_import_cycles, use_paths


class UseTest(unittest.TestCase):
    def test_a_use_tree_names_each_path(self) -> None:
        self.assertEqual(use_paths("crate::{a::X, b::{self, Y as Z}}"),
                         [["crate", "a", "X"], ["crate", "b"], ["crate", "b", "Y"]])


class CycleTest(BroomCase):
    def test_a_child_that_uses_its_parent_is_a_file_cycle_and_not_a_folder_one(self) -> None:
        r = self.repo({"src/lib.rs": "pub mod a;\n", "src/a.rs": "pub mod b;\npub use self::b::B;\n",
                       "src/a/b.rs": "use super::*;\npub struct B;\n"})
        self.assertEqual(rust_import_cycles(r, ["src/a/b.rs"]), [("src/a/b.rs", 1)])
        self.assertEqual(rust_folder_cycles(r, ["src/a/b.rs"]), [])

    def test_another_crate_and_test_code_lead_nowhere(self) -> None:
        r = self.repo({"src/lib.rs": "pub mod a;\nuse serde::a;\n",
                       "src/a.rs": "#[cfg(test)]\nmod tests {\n    use crate::*;\n}\n"})
        self.assertEqual(rust_import_cycles(r, ["src/lib.rs", "src/a.rs"]), [])


if __name__ == "__main__":
    unittest.main()
