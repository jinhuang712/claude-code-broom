"""Which TypeScript language server broom's launcher starts: one that can load a tsserver, else `tsc --lsp`."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from support import BroomCase


class TypescriptServerTest(BroomCase):
    def chosen(self, project: str = None, beside: str = None, *, on_path: bool = True, own: str = None,
               tsc: str = "7.0.2") -> tuple:
        """What typescript_server picks for a project with TypeScript `project`, a PATH server with `beside` beside
        it (none when not `on_path`), a global tsc of version `tsc` and, with `own`, broom's own server with that
        TypeScript beside it."""
        from unittest import mock
        from broom import depcruise
        from broom.lsp import typescript_server

        r = self.ts_install(project) if project else self.repo({"package.json": "{}\n"})
        env = self.fake_path(fakes={"tsc": f"echo 'Version {tsc}'"})
        if on_path:
            self.npm_server(env, beside)
        own_dir = self.tmp / f"own{uuid.uuid4().hex[:6]}"
        if own:
            exe = own_dir / "node_modules" / ".bin" / "typescript-language-server"
            exe.parent.mkdir(parents=True)
            exe.write_text("#!/bin/sh\n")
            exe.chmod(0o755)
            (own_dir / "node_modules" / "typescript").mkdir()
            (own_dir / "node_modules" / "typescript" / "package.json").write_text(json.dumps({"version": own}))
        with mock.patch.dict(os.environ, {"PATH": env["PATH"]}), mock.patch.object(depcruise, "OWN_DIR", own_dir):
            return typescript_server(r)

    def test_a_path_server_beside_typescript_7_is_not_picked_for_a_project_on_7(self) -> None:
        cmd, reason = self.chosen("7.0.1", "7.0.2")
        self.assertTrue(cmd[0].endswith("node_modules/.bin/tsc") and cmd[1:] == ["--lsp", "--stdio"], cmd)
        self.assertIn("gives Claude no diagnostics", reason)
        self.assertIn("beside the typescript-language-server", reason)
        self.assertIn("is 7.0.2, which has no tsserver", reason)

    def test_a_path_server_with_no_typescript_beside_is_not_picked_for_a_project_on_7_or_none(self) -> None:
        cmd, reason = self.chosen("7.0.1", None)
        self.assertTrue(cmd[0].endswith("node_modules/.bin/tsc"), cmd)
        self.assertIn("has no TypeScript beside it", reason)
        cmd, reason = self.chosen(None, None, tsc="5.9.3")
        self.assertIsNone(cmd)
        self.assertIn("has no TypeScript beside it", reason)

    def test_a_path_server_beside_typescript_6_is_picked_for_a_project_on_7_or_none(self) -> None:
        for project in ("7.0.1", None):
            cmd, reason = self.chosen(project, "6.0.3")
            self.assertEqual((Path(cmd[0]).name, cmd[1:]), ("typescript-language-server", ["--stdio"]), project)
            self.assertIn("the TypeScript 6.0.3 beside typescript-language-server", reason)
        self.assertIn("the project's TypeScript 7.0.1 has no tsserver", self.chosen("7.0.1", "6.0.3")[1])

    def test_a_path_server_is_picked_for_a_project_below_7_whatever_is_beside_it(self) -> None:
        for beside in (None, "7.0.2", "6.0.3"):
            cmd, reason = self.chosen("5.9.3", beside)
            self.assertEqual((Path(cmd[0]).name, cmd[1:]), ("typescript-language-server", ["--stdio"]), beside)
            self.assertIn("the project's TypeScript 5.9.3, through typescript-language-server", reason)

    def test_broom_s_own_server_comes_before_the_one_on_path(self) -> None:
        cmd, reason = self.chosen("7.0.1", "6.0.3", own="6.0.3")
        self.assertIn("/node_modules/.bin/typescript-language-server", cmd[0])
        self.assertIn(str(self.tmp), cmd[0])
        self.assertIn("beside typescript-language-server", reason)
        cmd, _ = self.chosen("7.0.1", None, on_path=False, own="6.0.3")
        self.assertIn(str(self.tmp), cmd[0])

    def test_a_path_server_is_tried_when_broom_s_own_cannot_start(self) -> None:
        cmd, reason = self.chosen("7.0.1", "6.0.3", own="7.0.2")
        self.assertEqual(Path(cmd[0]).name, "typescript-language-server")
        self.assertIn("the TypeScript 6.0.3 beside", reason)
        self.assertIn("/lib/node_modules/typescript-language-server/", os.path.realpath(cmd[0]))

    def test_no_server_that_can_start_leaves_the_global_typescript_7(self) -> None:
        cmd, reason = self.chosen(None, "7.0.2", tsc="7.0.2")
        self.assertEqual((Path(cmd[0]).name, cmd[1:]), ("tsc", ["--lsp", "--stdio"]))
        self.assertIn("the global TypeScript 7.0.2", reason)
        self.assertIn("is 7.0.2, which has no tsserver", reason)
