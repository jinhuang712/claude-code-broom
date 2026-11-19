"""Folders that import one another in a ring: the layers of the code going the wrong way."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from support import HAS_PY, BroomCase

from broom.foldercycles import Folders, js_folder_cycles, python_folder_cycles
from broom.smells import find_smells

PY_REPO = {
    "pkg/__init__.py": "",
    "pkg/auth/__init__.py": "",
    "pkg/auth/login.py": "VALUE = 1\n",
    "pkg/providers/__init__.py": "",
    "pkg/providers/github.py": "from pkg.auth import login\n\nTOKEN = login.VALUE\n",
    "pkg/ui/__init__.py": "",
    "pkg/ui/view.py": "from pkg.providers import github\n\nSHOWN = github.TOKEN\n",
}


class FolderGraphTests(unittest.TestCase):
    def test_a_folder_reaches_another_through_the_ones_between(self) -> None:
        folders = Folders(lambda d: {"a": ["b"], "b": ["c"], "c": [], "d": ["a"]}[d])
        self.assertTrue(folders.reaches("a", "c"))
        self.assertTrue(folders.reaches("d", "c"))
        self.assertFalse(folders.reaches("c", "a"))


class PythonFolderTests(BroomCase):
    def test_an_import_back_up_the_layers_is_found_where_it_is_added(self) -> None:
        r = self.repo(PY_REPO)
        self.assertEqual(python_folder_cycles(r, ["pkg/auth/login.py"]), [], "the layers go one way")
        (r / "pkg/auth/login.py").write_text("from pkg.ui import view\n\nVALUE = view.SHOWN\n")
        self.assertEqual(python_folder_cycles(r, ["pkg/auth/login.py"]), [("pkg/auth/login.py", 1)])

    def test_an_import_inside_a_function_is_the_way_out_and_does_not_count(self) -> None:
        r = self.repo(PY_REPO)
        (r / "pkg/auth/login.py").write_text("def view():\n    from pkg.ui import view\n    return view\n")
        self.assertEqual(python_folder_cycles(r, ["pkg/auth/login.py"]), [])

    def test_files_of_one_folder_importing_each_other_are_not_a_cycle_between_folders(self) -> None:
        r = self.repo({"pkg/__init__.py": "", "pkg/a.py": "from pkg import b\n", "pkg/b.py": "from pkg import a\n"})
        self.assertEqual(python_folder_cycles(r, ["pkg/a.py"]), [])

    @unittest.skipUnless(HAS_PY, "ruff")
    def test_the_smell_is_reported_on_the_line_the_change_added_and_only_there(self) -> None:
        r = self.repo(PY_REPO)
        (r / "pkg/auth/login.py").write_text("from pkg.ui import view\n\nVALUE = view.SHOWN\n")
        found, _ = find_smells(r, [r / "pkg/auth/login.py"], "HEAD")
        self.assertEqual([(s.metric, s.added, s.level) for s in found if s.metric == "folder_cycle"],
                         [("folder_cycle", [1], "hint")])



class JsFolderTests(BroomCase):
    def fake_depcruise(self, modules: list) -> dict:
        report = self.tmp / "report.json"
        report.write_text(json.dumps({"modules": modules}))
        return self.fake_path(fakes={"depcruise": f"cat {report}"}, keep=("cat",))

    def dep(self, resolved: str, module: str) -> dict:
        return {"resolved": resolved, "module": module, "couldNotResolve": False, "coreModule": False}

    def test_an_import_into_a_folder_that_imports_back_is_found_on_its_line(self) -> None:
        r = self.repo({"package.json": "{}", "src/auth/login.ts": "export const v = 1;\n",
                       "src/ui/view.ts": "export const s = 2;\n"})
        (r / "src/auth/login.ts").write_text('// the login\nimport { s } from "../ui/view";\nexport const v = s;\n')
        modules = [{"source": "src/auth/login.ts", "dependencies": [self.dep("src/ui/view.ts", "../ui/view")]},
                   {"source": "src/ui/view.ts", "dependencies": [self.dep("src/auth/login.ts", "../auth/login")]}]
        env = self.fake_depcruise(modules)
        notes: list = []
        with mock.patch.dict(os.environ, {"PATH": env["PATH"]}):
            self.assertEqual(js_folder_cycles(r, ["src/auth/login.ts"], notes, lambda: 60),
                             [("src/auth/login.ts", 2)])
        self.assertEqual(notes, [])

    def test_a_file_dependency_cruiser_did_not_read_is_said_so_not_taken_for_clean(self) -> None:
        r = self.repo({"package.json": "{}", "src/a.ts": "export const a = 1;\n"})
        env = self.fake_depcruise([{"source": "src/other.js", "dependencies": []}])
        notes: list = []
        with mock.patch.dict(os.environ, {"PATH": env["PATH"]}):
            self.assertEqual(js_folder_cycles(r, ["src/a.ts"], notes, lambda: 60), [])
        self.assertTrue(any("didn't read src/a.ts" in n and "TypeScript below 7" in n for n in notes), notes)
        self.assertFalse(any("npm i" in n for n in notes), "the user's TypeScript is not ours to change")

    def test_without_dependency_cruiser_nothing_is_measured_and_nothing_nags(self) -> None:
        r = self.repo({"package.json": "{}", "src/a.ts": "export const a = 1;\n"})
        notes: list = []
        with mock.patch.dict(os.environ, {"PATH": self.fake_path()["PATH"]}):
            self.assertEqual(js_folder_cycles(r, ["src/a.ts"], notes, lambda: 60), [])
        self.assertEqual(notes, [], "broom doctor offers it; a note on every check would nag")


if __name__ == "__main__":
    unittest.main()
