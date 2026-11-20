"""The `use` graph of Rust files behind the import and folder cycles: how a path is read, and which cycles count.
Sample code is a list of lines, so that none of it stands in this file as code of its own."""

from __future__ import annotations

import shutil
import unittest

from support import BroomCase

from broom.rustcycles import rust_folder_cycles, rust_import_cycles, use_path
from broom.rustmeasure import rust_tree


@unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
class UseTest(BroomCase):
    def test_a_use_tree_names_each_path_and_a_comment_or_string_names_none(self) -> None:
        (self.tmp / "a.rs").write_text("\n".join(["use crate::{a::X, b::{self, Y as Z}};", "pub use self::m::*;",
                                                  "// use crate::hidden;", 'const S: &str = "use crate::nope;";',
                                                  "use crate::{", "    multi::Line,", "};", ""]))
        found = [m for m in rust_tree(self.tmp, ["a.rs"], [])["a.rs"] if m.rule.startswith("rust-use-")]
        self.assertEqual(sorted((m.line, use_path(m)) for m in found),
                         [(1, ["crate", "a", "X"]), (1, ["crate", "b"]), (1, ["crate", "b", "Y"]), (2, ["m"]),
                          (6, ["crate", "multi", "Line"])])


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
