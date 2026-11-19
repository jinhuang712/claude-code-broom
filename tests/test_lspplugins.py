"""Enabled plugins whose language server competes with broom's, found from what each plugin declares."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Dict, Optional

from support import BroomCase

TS = {".ts": "typescript", ".tsx": "typescriptreact"}
JAVA = {".java": "java"}


class LspPluginsTest(BroomCase):
    def install(self, plugins: Dict[str, Optional[dict]], *, enable: Optional[list] = None, installed: bool = True) -> dict:
        """An env whose Claude config enables `enable` (default: every plugin of `plugins`), with a plugin folder per
        plugin: its `lspServers` is the value in `plugins` (None: no folder is written, though it is installed)."""
        env = self.fake_path()
        config = self.config_dir({"enabledPlugins": {k: True for k in enable or plugins}})
        entries = {}
        for key, claims in plugins.items():
            folder = self.tmp / "installs" / key.split("@")[0]
            if claims is not None:
                (folder / ".claude-plugin").mkdir(parents=True)
                server = {"command": "x", "extensionToLanguage": claims}
                (folder / ".claude-plugin" / "plugin.json").write_text(
                    json.dumps({"name": key.split("@")[0], "lspServers": {"x": server}}))
            entries[key] = [{"scope": "user", "installPath": str(folder)}]
        if installed:
            (config / "plugins").mkdir()
            (config / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": entries}))
        return env

    def conflicts(self, repo: Path, env: dict) -> list:
        return [(i["lang"], i["tool"], i["fix"]) for i in self.doctor(repo, env)["items"] if i["status"] == "conflict"]

    def test_a_plugin_under_an_unknown_name_that_declares_typescript_is_a_conflict(self) -> None:
        env = self.install({"fast-ts@market": TS})
        self.assertEqual(self.conflicts(self.ts_repo(), env),
                         [("js", "fast-ts@market", "claude plugin disable fast-ts@market")])

    def test_a_plugin_that_declares_only_java_is_none(self) -> None:
        env = self.install({"jdtls-x@market": JAVA})
        self.assertEqual(self.conflicts(self.ts_repo(), env), [])

    def test_a_typescript_plugin_conflicts_in_a_repo_with_no_typescript(self) -> None:
        env = self.install({"fast-ts@market": TS})
        r = self.repo({"tools/sync.py": "print(1)\n"})
        self.assertEqual(self.conflicts(r, env), [("js", "fast-ts@market", "claude plugin disable fast-ts@market")])
        out = self.cli(r, "doctor", env=env).stdout
        self.assertIn("fast-ts@market", out)
        self.assertIn("claude plugin disable fast-ts@market", out)
        checks = json.loads(self.cli(r, "doctor", "--checks", "--json", env=env).stdout)["checks"]
        gaps = [c for c in checks if c["tool"] == "fast-ts@market"]
        self.assertEqual([(c["language"], c["status"]) for c in gaps], [("js", "off")],
                         "a conflict for a language the repo lacks is listed with the repo's own gaps")
        text = self.cli(r, "doctor", "--checks", env=env).stdout
        self.assertIn("Beside the languages:", text)
        self.assertIn("fast-ts@market", text.split("Beside the languages:")[1])

    def test_a_plugin_that_cannot_be_read_is_judged_by_its_name(self) -> None:
        env = self.install({"typescript-lsp@official": None, "other@market": None})
        self.assertEqual(self.conflicts(self.ts_repo(), env),
                         [("js", "typescript-lsp@official", "claude plugin disable typescript-lsp@official")])
        env = self.install({"gopls-lsp@official": None}, installed=False)
        self.assertEqual([c[:2] for c in self.conflicts(self.repo({"a.py": "A = 1\n"}), env)],
                         [("go", "gopls-lsp@official")], "a plugin that isn't located is judged by its name too")

    def test_a_plugin_that_serves_one_of_broom_s_languages_among_others_is_a_conflict_for_that_one(self) -> None:
        env = self.install({"many@market": {".c": "c", ".py": "python", ".rs": "rust"}})
        self.assertEqual([c[:2] for c in self.conflicts(self.ts_repo(), env)],
                         [("py", "many@market"), ("rust", "many@market")])

    def test_broom_itself_and_a_disabled_plugin_are_no_conflict(self) -> None:
        env = self.install({"broom@market": TS, "off@market": TS}, enable=["broom@market"])
        self.assertEqual(self.conflicts(self.ts_repo(), env), [])


if __name__ == "__main__":
    unittest.main()
