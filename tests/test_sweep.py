"""The edit and stop hooks, `broom sweep` and its scopes, and how much a format touches."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from support import (
    BROOM, HAS_GO, HAS_GOPLS, HAS_PY, HAS_PYRIGHT, HAS_TS, TS_BAD, BroomCase,
)

from broom.fmt import keep_hunks


class SweepTest(BroomCase):
    # edit and stop modes

    @unittest.skipUnless(HAS_GO, "go tools missing")
    def test_edit_hook_is_idle_unless_enabled(self) -> None:
        r = self.go_repo()
        f = r / "internal/util/z.go"
        f.write_text("package util\nfunc  Z( ) {  }\n")
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Write", "tool_input": {"file_path": str(f)}}
        self.assertEqual(self.hook("edit", payload), {})
        self.assertIn("func  Z", f.read_text())
        self.assertEqual(self.hook("edit", payload, format_on="edit"), {})
        self.assertEqual(f.read_text(), "package util\n\nfunc Z() {}\n")

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_sweep_cli(self) -> None:
        r = self.repo({"a.py": "def f(x):\n    return x\n"})
        (r / "a.py").write_text("import os\n\ndef f(x):\n    return x\n")
        p = subprocess.run([str(BROOM), "sweep", "--check"], cwd=r, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("F401", p.stdout)

    # sweep scopes

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_sweep_base_counts_only_lines_from_those_commits(self) -> None:
        r = self.repo({"a.py": "import os\n"})
        (r / "a.py").write_text("import os\nimport sys\n")
        self.sh(r, "git", "commit", "-qam", "add sys")
        out = self.cli(r, "sweep", "--check", "--base", "HEAD~1").stdout
        self.assertIn("`sys` imported but unused", out)
        self.assertNotIn("`os`", out)

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_sweep_all_reports_old_issues_and_formats_only_with_fix(self) -> None:
        ugly = "import os\nx = {  'a':1 }\n"
        r = self.repo({"ruff.toml": "", "a.py": ugly})
        out = self.cli(r, "sweep", "--all").stdout
        self.assertIn("`os` imported but unused", out)
        self.assertEqual((r / "a.py").read_text(), ugly, "--all alone reports only")
        self.cli(r, "sweep", "--all", "--fix")
        self.assertEqual((r / "a.py").read_text(), 'import os\n\nx = {"a": 1}\n')

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_sweep_summarizes_big_results(self) -> None:
        r = self.repo({"a.py": "".join(f"import mod{n}\n" for n in range(60))})
        out = self.cli(r, "sweep", "--all").stdout
        self.assertIn("Most frequent: ruff F401 ×60", out)
        self.assertIn("... and 20 more", out)

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_known_issues_are_listed_hidden_and_clearable(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_BAD)
        self.sh(r, "git", "add", "src/main.ts")
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.cli(r, "known", "--accept", "demo code").returncode, 0)
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        listed = self.cli(r, "known").stdout
        self.assertIn("no-floating-promises", listed)
        self.assertIn("(demo code)", listed)
        self.assertIn("main.ts:5", listed)
        self.assertIn("known issue(s) hidden", self.cli(r, "sweep", "--check").stdout)
        self.assertIn("cleared 2", self.cli(r, "known", "--clear").stdout)
        self.assertTrue(self.denied(self.commit(r, "git commit -m x")), "cleared issues block again")

    # format scope

    def test_keep_hunks_undoes_edits_away_from_changed_lines(self) -> None:
        self.assertEqual(keep_hunks("a\nb\nc\n", "A\nb\nC\n", {3}), "a\nb\nC\n")
        self.assertEqual(keep_hunks("a\nc\n", "a\nb\nc\n", {2}), "a\nb\nc\n", "insertion next to a changed line")
        self.assertEqual(keep_hunks("a\nc\n", "a\nb\nc\n", {9}), "a\nc\n")
        self.assertEqual(keep_hunks("a\nb\n", "a\n", {2}), "a\n", "deletion of a changed line")

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_changed_scope_formats_only_the_changed_lines(self) -> None:
        old = "a = {  'x':1 }\n"
        for scope, expected in (("changed", old + 'b = {"y": 2}\n'), ("file", 'a = {"x": 1}\nb = {"y": 2}\n')):
            r = self.repo({"ruff.toml": "", "m.py": old})
            (r / "m.py").write_text(old + "b = {  'y':2 }\n")
            self.sh(r, "git", "add", "m.py")
            self.commit(r, "git commit -m b", format_scope=scope)
            self.assertEqual((r / "m.py").read_text(), expected, scope)
            self.assertEqual(self.sh(r, "git", "show", ":m.py"), expected, f"{scope}: re-staged")

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_cli_reads_options_from_the_settings_file(self) -> None:
        """Bash-run broom doesn't get CLAUDE_PLUGIN_OPTION_*; it reads pluginConfigs instead."""
        old = "a = {  'x':1 }\n"
        r = self.repo({"ruff.toml": "", "m.py": old})
        (r / "m.py").write_text(old + "b = {  'y':2 }\n")
        cfg = self.config_dir({"pluginConfigs": {"broom@claude-code-broom": {"options": {"format_scope": "file"}}}})
        self.cli(r, "fmt", env={**self.env, "CLAUDE_CONFIG_DIR": str(cfg)})
        self.assertEqual((r / "m.py").read_text(), 'a = {"x": 1}\nb = {"y": 2}\n')
        (r / "m.py").write_text(old + "b = {  'y':2 }\n")
        self.cli(r, "fmt", "--scope", "changed", env={**self.env, "CLAUDE_CONFIG_DIR": str(cfg)})
        self.assertEqual((r / "m.py").read_text(), old + 'b = {"y": 2}\n', "--scope overrides the setting")

    # function scope

    PY_TWO_FUNCS = "def f():\n    a = {  'x':1 }\n    return a\n\n\ndef g():\n    b = {  'y':2 }\n    return b\n"

    def py_touched(self) -> Path:
        r = self.repo({"ruff.toml": "", "m.py": self.PY_TWO_FUNCS})
        (r / "m.py").write_text(self.PY_TWO_FUNCS.replace("    return a\n", "    return a  # touched\n"))
        return r

    @unittest.skipUnless(HAS_PYRIGHT, "ruff/pyright missing")
    def test_function_scope_formats_the_whole_changed_function_only(self) -> None:
        r = self.py_touched()
        self.cli(r, "fmt", "--scope", "function")
        text = (r / "m.py").read_text()
        self.assertIn('a = {"x": 1}', text, "the changed function is formatted")
        self.assertIn("b = {  'y':2 }", text, "the untouched function is not")
        r = self.py_touched()
        self.cli(r, "fmt", "--scope", "changed")
        self.assertIn("a = {  'x':1 }", (r / "m.py").read_text(), "changed scope leaves the rest of f alone")

    @unittest.skipUnless(HAS_GOPLS, "gopls missing")
    def test_function_scope_with_gopls(self) -> None:
        src = "package m\n\nfunc F() int {\n\tx := 1\n\treturn  x\n}\n\nfunc G() int {\n\ty := 2\n\treturn  y\n}\n"
        r = self.repo({"go.mod": "module example.com/m\n\ngo 1.26\n", "m.go": src})
        (r / "m.go").write_text(src.replace("x := 1", "x := 3"))
        self.cli(r, "fmt", "--scope", "function")
        text = (r / "m.go").read_text()
        self.assertIn("\treturn x\n", text)
        self.assertIn("\treturn  y\n", text)

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_function_scope_falls_back_to_changed_lines_without_a_server(self) -> None:
        r = self.py_touched()
        out = self.cli(r, "fmt", "--scope", "function", env=self.fake_path(keep=("ruff",))).stdout
        self.assertIn("no language server answered", out)
        self.assertIn("a = {  'x':1 }", (r / "m.py").read_text())
