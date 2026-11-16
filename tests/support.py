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

import isolation  # first: it gives the run a data directory of its own, before broom fixes one
from broom.toolchain import swift_format_cmd

ROOT = isolation.ROOT
BROOM = isolation.BROOM

CARD = "broom's bar in this repo"  # how the limits card, told at session start, begins
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
def runs(cmd: list) -> bool:
    """Whether `cmd` exits 0: a tool can be on the PATH and not run, as a version manager's shim with no version."""
    try:
        return shutil.which(cmd[0]) is not None and subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


HAS_SWIFTFORMAT = runs(["swiftformat", "--version"])


def swift_format_runs() -> bool:
    cmd = swift_format_cmd()
    return bool(cmd) and subprocess.run([*cmd, "--version"], capture_output=True).returncode == 0


HAS_SWIFT_FORMAT = swift_format_runs()
HAS_SOURCEKIT = HAS_SWIFT_FORMAT and shutil.which("sourcekit-lsp") is not None


def py_function(name: str, lines: int) -> str:
    """A Python function `lines` long; the same name and length give the same body, so two are a clone."""
    body = "".join(f"    x += {i}\n" for i in range(lines - 2))
    return f"def {name}(x):\n{body}    return x\n"


# Code the commit, doctor and sweep tests share.
GO_MAIN = """package main

import (
\t"fmt"

\t"example.com/m/internal/util"
)

func main() { fmt.Println(util.Add(1, 2)) }
"""
GO_UTIL = """package util

func Add(a, b int) int { return a + b }
"""
TS_LIB = """export async function fetchIt(n: number): Promise<number> {
  return n * 2;
}
"""
TS_MAIN = """import { fetchIt } from "./lib.js";

export async function run(): Promise<number> {
  return await fetchIt(1);
}
"""
TS_BAD = """import { fetchIt } from "./lib.js";

export async function run(): Promise<number> {
  const unused = 5;
  fetchIt(3);
  return await fetchIt(1);
}
"""



class BroomCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_PLUGIN_", "GIT_"))}
        # An empty Claude config, so the real user settings (broom's options, enabled plugins) never leak in.
        self.env = {**env, **GIT_ENV, "CLAUDE_PLUGIN_DATA": str(self.tmp / "data"),
                    "CLAUDE_CONFIG_DIR": str(self.config_dir())}
        # The data directory of this process is the hooks' too, one per test: what a measurement found is kept by
        # content, and one test's must not stand in for another's, which may run the same text with a tool broken.
        self.addCleanup(isolation.repoint(isolation.PATHS, self.tmp / "data").close)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual(isolation.take_violations(), [], "a test wrote into the user's own data directory")

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

    def session(self, repo: Path, session_id: str, env: dict, event: str = "session") -> dict:
        """A session-start hook: `session`, or the async `session-scan`."""
        r = subprocess.run([str(BROOM), "hook", event], capture_output=True, text=True, env=env,
                           input=json.dumps({"session_id": session_id, "cwd": str(repo), "source": "startup"}))
        self.assertEqual(r.stderr.strip(), "", "hook raised")
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def noted(self, out: dict) -> str:
        """What a session hook told Claude besides the limits card, which every repo with code gets once a session."""
        text = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        return "\n\n".join(x for x in text.split("\n\n") if not x.startswith(CARD))

    def doctor(self, repo: Path, env: dict) -> dict:
        return json.loads(self.cli(repo, "doctor", "--json", env=env).stdout)

    def denied(self, out: dict) -> str:
        spec = out.get("hookSpecificOutput", {})
        return spec.get("permissionDecisionReason", "") if spec.get("permissionDecision") == "deny" else ""

    # repos with code

    def go_repo(self) -> Path:
        return self.repo({"go.mod": "module example.com/m\n\ngo 1.26\n", "cmd/app/main.go": GO_MAIN,
                          "internal/util/util.go": GO_UTIL})

    def ts_repo(self, extra: dict = None) -> Path:
        return self.repo({"package.json": '{"name":"t","private":true,"type":"module"}\n',
                          "tsconfig.json": '{"compilerOptions":{"target":"es2022","module":"nodenext","strict":true,'
                                           '"noEmit":true},"include":["src"]}\n',
                          "src/lib.ts": TS_LIB, "src/main.ts": TS_MAIN, **(extra or {})})
