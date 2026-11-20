"""A file's imports, read from its syntax tree: an `import` in a string or a comment is none."""

from __future__ import annotations

import shutil
import unittest

from support import BroomCase

from broom.foldercycles import import_line
from broom.imports import import_lines, import_sources


class ImportsTest(BroomCase):
    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_imports_are_read_from_the_tree_however_wrapped(self) -> None:
        ts = ('import {\n  a,\n  b,\n} from "./x";\nimport c from "c";\nexport { d } from "./d";\n'
              'const e = require("e");\n\nexport const f = a + b;\n')
        calls = 'run(require("x"), () => {\n  go();\n});\nimport("./y").then((m) => {\n  m.go();\n});\n'
        quoted = 'const s = `\nimport x from "y";\n`;\n// import z from "w";\n'
        py = '"""Doc.\n\nfrom the base\nimport os\n"""\nimport os\nfrom a import (\n    b,\n)\n'
        found = import_lines({"m.ts": ts, "calls.ts": calls, "quoted.js": quoted, "m.py": py,
                              "m.go": 'package m\n\nimport (\n\t"fmt"\n\t"os"\n)\n\nfunc F() {}\n', "m.rs": "use a;\n"}, [])
        self.assertEqual(found["m.ts"], 7)
        self.assertEqual(found["calls.ts"], 0, "a call that requires or imports in passing is code")
        self.assertEqual(found["quoted.js"], 0, "an import in a string or a comment is none")
        self.assertEqual(found["m.py"], 4, "prose isn't an import, even one that reads like one")
        self.assertEqual(found["m.go"], 4)
        self.assertEqual(found["m.rs"], 0, "a language whose imports broom doesn't read: none")

    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep missing")
    def test_the_line_is_the_import_naming_the_module_never_a_string_or_a_comment(self) -> None:
        (self.tmp / "a.ts").write_text(
            'const s = "../b/x";\n// import y from "../b/x";\nimport {\n  y,\n} from "../b/x";\n'
            'export * from "../c";\nconst d = require("../d");\nconst e = () => import(`../e`);\n')
        found = import_sources(self.tmp, ["a.ts"], [])["a.ts"]
        self.assertEqual(found, [(5, "../b/x"), (6, "../c"), (7, "../d"), (8, "../e")])
        self.assertEqual(import_line(found, ["../b/x"]), 5)
        self.assertEqual(import_line(found, ["../e", "../d"]), 7)
        self.assertEqual(import_line(found, ["../f"]), 0)


if __name__ == "__main__":
    unittest.main()
