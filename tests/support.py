"""Shared test support: paths, which tools are installed, and a TestCase base with throwaway repos and
runners for broom's hooks and command line."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BROOM = ROOT / "bin" / "broom"
sys.path.insert(0, str(ROOT / "lib"))

from broom.common import swift_format_cmd  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
HAS_GO = all(shutil.which(t) for t in ("go", "gofmt", "golangci-lint"))
HAS_TS = all(shutil.which(t) for t in ("oxlint", "tsc"))
HAS_PY = shutil.which("ruff") is not None
HAS_GOPLS = HAS_GO and shutil.which("gopls") is not None
HAS_PYRIGHT = HAS_PY and shutil.which("pyright-langserver") is not None
HAS_STYLELINT = shutil.which("stylelint") is not None
HAS_CSS_LSP = shutil.which("vscode-css-language-server") is not None and shutil.which("oxfmt") is not None
HAS_SWIFT = shutil.which("swift") is not None
HAS_SWIFTLINT = shutil.which("swiftlint") is not None
HAS_SWIFTFORMAT = shutil.which("swiftformat") is not None


def swift_format_runs() -> bool:
    cmd = swift_format_cmd()
    return bool(cmd) and subprocess.run([*cmd, "--version"], capture_output=True).returncode == 0


HAS_SWIFT_FORMAT = swift_format_runs()
HAS_SOURCEKIT = HAS_SWIFT_FORMAT and shutil.which("sourcekit-lsp") is not None


class BroomCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_PLUGIN_", "GIT_"))}
        # An empty Claude config, so the real user settings (broom's options, enabled plugins) never leak in.
        self.env = {**env, **GIT_ENV, "CLAUDE_PLUGIN_DATA": str(self.tmp / "data"),
                    "CLAUDE_CONFIG_DIR": str(self.config_dir())}

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers

    def sh(self, cwd: Path, *cmd: str) -> str:
        r = subprocess.run(cmd, cwd=cwd, env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def repo(self, files: dict) -> Path:
        d = self.tmp / f"repo{uuid.uuid4().hex[:6]}"
        for name, text in files.items():
            (d / name).parent.mkdir(parents=True, exist_ok=True)
            (d / name).write_text(text)
        self.sh(d, "git", "init", "-q")
        self.sh(d, "git", "add", "-A")
        self.sh(d, "git", "commit", "-qm", "init")
        return d

    def hook(self, event: str, payload: dict, cwd: Path = None, **options: str) -> dict:
        env = {**self.env, **{f"CLAUDE_PLUGIN_OPTION_{k.upper()}": v for k, v in options.items()}}
        r = subprocess.run([str(BROOM), "hook", event], input=json.dumps(payload), capture_output=True, text=True,
                           env=env, cwd=cwd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr.strip(), "", "hook raised")
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def commit(self, repo: Path, command: str, tool_use_id: str = None, **options: str) -> dict:
        return self.hook("commit", {"session_id": "s1", "cwd": str(repo), "hook_event_name": "PreToolUse",
                                    "tool_name": "Bash", "tool_input": {"command": command},
                                    "tool_use_id": tool_use_id or uuid.uuid4().hex}, **options)

    def cli(self, cwd: Path, *args: str, env: dict = None) -> subprocess.CompletedProcess:
        return subprocess.run([str(BROOM), *args], cwd=cwd, env=env or self.env, capture_output=True, text=True)

    def fake_path(self, keep: tuple = (), fakes: dict = None) -> dict:
        """An env whose PATH holds only git, python3, the `keep` tools and `fakes` scripts, so tools look missing
        or broken. CLAUDE_CONFIG_DIR points at an empty config so real plugin settings don't leak in."""
        d = self.tmp / f"bin{uuid.uuid4().hex[:6]}"
        d.mkdir()
        (d / "python3").symlink_to(sys.executable)
        for name in ("git", *keep):
            if shutil.which(name):
                (d / name).symlink_to(shutil.which(name))
        for name, body in (fakes or {}).items():
            (d / name).write_text("#!/bin/sh\n" + body + "\n")
            (d / name).chmod(0o755)
        return {**self.env, "PATH": str(d), "CLAUDE_CONFIG_DIR": str(self.config_dir())}

    def config_dir(self, settings: dict = None) -> Path:
        d = self.tmp / "claude-config"
        d.mkdir(exist_ok=True)
        (d / "settings.json").write_text(json.dumps(settings or {}))
        return d

    def session(self, repo: Path, session_id: str, env: dict) -> dict:
        r = subprocess.run([str(BROOM), "hook", "session"], capture_output=True, text=True, env=env,
                           input=json.dumps({"session_id": session_id, "cwd": str(repo), "source": "startup"}))
        self.assertEqual(r.stderr.strip(), "", "hook raised")
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def doctor(self, repo: Path, env: dict) -> dict:
        return json.loads(self.cli(repo, "doctor", "--json", env=env).stdout)

    def denied(self, out: dict) -> str:
        spec = out.get("hookSpecificOutput", {})
        return spec.get("permissionDecisionReason", "") if spec.get("permissionDecision") == "deny" else ""

