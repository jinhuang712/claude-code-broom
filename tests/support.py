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
from unittest import mock

import isolation  # first: it gives the run a data directory of its own, before broom fixes one
from broom.toolchain import swift_format_cmd

ROOT = isolation.ROOT
BROOM = isolation.BROOM

# What an idle hook has no use for: the command line, the linters and the commit gate, with all they import.
HEAVY = ("broom.cli", "broom.checks", "broom.commitgate", "broom.smells", "broom.doctor")
CARD = "broom's bar in this repo"  # how the limits card, told at session start, begins
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
# The 25 seconds one hook run may take are what a cold swift build uses up when other test files hold the cores: the
# check is then skipped for a while and the next commit passes. A test of the budget sets its own.
TEST_HOOK_SECONDS = "120"
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


def no_depcruise():
    """A patch that hides dependency-cruiser from the folder-cycle check, for a test of other tools: one installed on
    the machine adds a note of its own, and with a TypeScript 7 beside it a note that it read no .ts file."""
    return mock.patch("broom.foldercycles.pick", return_value=None)


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
                    "CLAUDE_CONFIG_DIR": str(self.config_dir()), "BROOM_HOOK_SECONDS": TEST_HOOK_SECONDS}
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

    def counted(self, event: str, payload: dict, repo: Path) -> tuple:
        """Run a hook as Claude Code does: the git commands it started, and the modules of broom it loaded."""
        shim = self.tmp / "shim"
        shim.mkdir(exist_ok=True)
        log = self.tmp / "git.log"
        log.write_text("")
        (shim / "git").write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexec "{shutil.which("git")}" "$@"\n')
        (shim / "git").chmod(0o755)
        env = {**self.env, "PATH": f"{shim}:{self.env['PATH']}"}
        r = subprocess.run([sys.executable, "-X", "importtime", str(BROOM), "hook", event], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, cwd=repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        loaded = [row.rsplit("|", 1)[1].strip() for row in r.stderr.splitlines() if row.startswith("import time:")]
        self.assertEqual([row for row in r.stderr.splitlines() if not row.startswith("import time:")], [], "raised")
        return log.read_text().splitlines(), [m for m in loaded if m.startswith("broom")]


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

    def npm_depcruise(self, env: dict, typescript: str = None, *, own: bool = False) -> dict:
        """`env` with a dependency-cruiser on its PATH as a global npm install puts one: a symlink to a script in
        <prefix>/lib/node_modules/dependency-cruiser/bin, with the `typescript` package of version `typescript`
        beside the package (inside it with `own`), or none."""
        modules = self.tmp / f"npm{uuid.uuid4().hex[:6]}" / "lib" / "node_modules"
        script = modules / "dependency-cruiser" / "bin" / "dependency-cruiser.mjs"
        script.parent.mkdir(parents=True)
        script.write_text('#!/bin/sh\necho "18.8.0"\n')
        script.chmod(0o755)
        if typescript:
            home = modules / "dependency-cruiser" / "node_modules" if own else modules
            (home / "typescript").mkdir(parents=True)
            (home / "typescript" / "package.json").write_text(json.dumps({"name": "typescript", "version": typescript}))
        for name in ("depcruise", "dependency-cruiser"):
            (Path(env["PATH"]) / name).symlink_to(script)
        return env

    def own_depcruise(self) -> str:
        """broom's own dependency-cruiser, as `npm i --prefix` leaves it in the test run's data directory; returns the
        command that installs it."""
        own = self.tmp / "data" / "node"
        exe = own / "node_modules" / ".bin" / "depcruise"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text('#!/bin/sh\necho "18.8.0"\n')
        exe.chmod(0o755)
        return self.own_install(own)

    def own_install(self, own: Path = None) -> str:
        """The command that installs broom's own dependency-cruiser into the test run's data directory."""
        return f'npm i --prefix "{own or self.tmp / "data" / "node"}" dependency-cruiser typescript@6'

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
