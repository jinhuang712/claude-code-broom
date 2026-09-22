"""End-to-end tests: throwaway git repos, hooks fed the JSON Claude Code sends.

Run: python3 -m unittest discover -s tests -v
Tests for a language are skipped when its tools aren't installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BROOM = ROOT / "bin" / "broom"
sys.path.insert(0, str(ROOT / "lib"))

from broom.fmt import keep_hunks  # noqa: E402
from broom.gitcmd import GitOp, parse, parse_commit  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
HAS_GO = all(shutil.which(t) for t in ("go", "gofmt", "golangci-lint"))
HAS_TS = all(shutil.which(t) for t in ("oxlint", "tsc"))
HAS_PY = shutil.which("ruff") is not None
HAS_GOPLS = HAS_GO and shutil.which("gopls") is not None
HAS_PYRIGHT = HAS_PY and shutil.which("pyright-langserver") is not None

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


class BroomTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_PLUGIN_", "GIT_"))}
        self.env = {**env, **GIT_ENV, "CLAUDE_PLUGIN_DATA": str(self.tmp / "data")}

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

    def go_repo(self) -> Path:
        return self.repo({"go.mod": "module example.com/m\n\ngo 1.26\n", "cmd/app/main.go": GO_MAIN,
                          "internal/util/util.go": GO_UTIL})

    def ts_repo(self, extra: dict = None) -> Path:
        return self.repo({"package.json": '{"name":"t","private":true,"type":"module"}\n',
                          "tsconfig.json": '{"compilerOptions":{"target":"es2022","module":"nodenext","strict":true,'
                                           '"noEmit":true},"include":["src"]}\n',
                          "src/lib.ts": TS_LIB, "src/main.ts": TS_MAIN, **(extra or {})})

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

    # command parsing

    def test_parse_heredoc_message_flags_do_not_count(self) -> None:
        cmd = "cd sub && git add -A && git commit -am \"$(cat <<'EOF'\nfix -n handling --no-verify\nEOF\n)\""
        ops = parse(cmd, self.tmp)
        self.assertEqual([o.kind for o in ops], ["add", "commit"])
        self.assertEqual(ops[1].cwd, (self.tmp / "sub").resolve())
        spec = parse_commit(ops[1])
        self.assertTrue(spec.all)
        self.assertFalse(spec.no_verify)

    def test_parse_git_dash_c_and_options(self) -> None:
        ops = parse("git -C other -c core.x=1 commit -n --author 'A <a@b>' -m x", self.tmp)
        self.assertEqual(ops[0].cwd, (self.tmp / "other").resolve())
        spec = parse_commit(ops[0])
        self.assertTrue(spec.no_verify)
        self.assertEqual(spec.pathspecs, [])
        self.assertEqual(parse_commit(GitOp("commit", self.tmp, ["-m", "msg", "--", "a.go"])).pathspecs, ["a.go"])
        self.assertEqual(parse("git status && echo commit", self.tmp), [])

    # commit hook: TypeScript

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_commit_denied_then_same_result_passes(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_BAD)
        self.sh(r, "git", "add", "src/main.ts")
        reason = self.denied(self.commit(r, "git commit -m wip"))
        self.assertIn("no-floating-promises", reason)
        self.assertIn("no-unused-vars", reason)
        again = self.commit(r, "git commit -m wip")
        self.assertEqual(self.denied(again), "")
        self.assertIn("known issue", again["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.denied(self.commit(r, "git commit -m wip")), "", "known issues stay known")

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_commit_passes_after_fix(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_BAD)
        self.sh(r, "git", "add", "src/main.ts")
        self.assertTrue(self.denied(self.commit(r, "git commit -m wip")))
        (r / "src/main.ts").write_text(TS_MAIN.replace("fetchIt(1)", "fetchIt(2)"))
        self.sh(r, "git", "add", "src/main.ts")
        self.assertEqual(self.commit(r, "git commit -m fixed"), {})

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_type_error_blocks(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_MAIN.replace("fetchIt(1)", 'fetchIt("1")'))
        self.sh(r, "git", "add", "src/main.ts")
        self.assertIn("TS2345", self.denied(self.commit(r, "git commit -m x")))

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_solution_style_tsconfig_checks_its_references(self) -> None:
        r = self.ts_repo({"tsconfig.app.json": '{"compilerOptions":{"target":"es2022","module":"nodenext",'
                                               '"strict":true,"composite":true},"include":["src"]}\n'})
        (r / "tsconfig.json").write_text('{"files":[],"references":[{"path":"./tsconfig.app.json"}]}\n')
        (r / "src/main.ts").write_text(TS_MAIN.replace("fetchIt(1)", 'fetchIt("1")'))
        self.sh(r, "git", "add", "-A")
        self.assertIn("TS2345", self.denied(self.commit(r, "git commit -m x")))

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_add_in_the_same_command_is_predicted(self) -> None:
        r = self.ts_repo()
        (r / "src/new.ts").write_text(TS_BAD)
        self.assertEqual(self.commit(r, "git commit -m nothing-staged"), {})
        self.assertIn("new.ts", self.denied(self.commit(r, "git add . && git commit -m x")))

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_commit_all_takes_unstaged_changes(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_BAD)
        self.assertIn("main.ts", self.denied(self.commit(r, "git commit -am x")))

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_no_verify_and_non_commits_are_left_alone(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_BAD)
        self.sh(r, "git", "add", "src/main.ts")
        self.assertEqual(self.commit(r, "git commit --no-verify -m x"), {})
        self.assertEqual(self.commit(r, f"git -C {r} status"), {})
        self.assertTrue(self.denied(self.commit(r, f"git -C {r} commit -m x")))

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_one_tool_call_is_checked_once(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_BAD)
        self.sh(r, "git", "add", "src/main.ts")
        self.assertTrue(self.denied(self.commit(r, "git commit -m x", tool_use_id="same")))
        self.assertEqual(self.commit(r, "git commit -m x", tool_use_id="same"), {})

    @unittest.skipUnless(HAS_TS and shutil.which("oxfmt"), "oxfmt missing")
    def test_oxfmt_project_is_formatted_at_commit(self) -> None:
        r = self.ts_repo({".oxfmtrc.json": "{}\n"})
        (r / "src/extra.ts").write_text("export const  y = {a:1,\n b:2}\n")
        self.sh(r, "git", "add", "src/extra.ts")
        out = self.commit(r, "git commit -m x")
        self.assertEqual(self.denied(out), "")
        self.assertEqual((r / "src/extra.ts").read_text(), "export const y = { a: 1, b: 2 };\n")
        self.assertEqual(self.sh(r, "git", "diff", "--name-only"), "", "the formatted file was re-staged")

    # commit hook: Go

    @unittest.skipUnless(HAS_GO, "go tools missing")
    def test_go_formatted_and_restaged(self) -> None:
        r = self.go_repo()
        (r / "internal/util/z.go").write_text("package util\nfunc  Z( ) {  }\n")
        self.sh(r, "git", "add", "internal/util/z.go")
        out = self.commit(r, "git commit -m z")
        self.assertEqual(self.denied(out), "")
        self.assertIn("gofmt", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual((r / "internal/util/z.go").read_text(), "package util\n\nfunc Z() {}\n")
        self.assertIn("func Z() {}", self.sh(r, "git", "show", ":internal/util/z.go"))
        self.assertEqual(self.sh(r, "git", "diff", "--name-only"), "")

    @unittest.skipUnless(HAS_GO, "go tools missing")
    def test_partially_staged_file_is_not_formatted(self) -> None:
        r = self.go_repo()
        bad = "package util\nfunc  Z( ) {  }\n"
        (r / "internal/util/z.go").write_text(bad)
        self.sh(r, "git", "add", "internal/util/z.go")
        (r / "internal/util/z.go").write_text(bad + "func  W( ) {  }\n")
        out = self.commit(r, "git commit -m z")
        self.assertEqual((r / "internal/util/z.go").read_text(), bad + "func  W( ) {  }\n")
        self.assertEqual(self.sh(r, "git", "show", ":internal/util/z.go"), bad)
        self.assertIn("partially staged", out["hookSpecificOutput"]["additionalContext"])

    @unittest.skipUnless(HAS_GO, "go tools missing")
    def test_go_broken_caller_in_another_package_blocks(self) -> None:
        r = self.go_repo()
        (r / "internal/util/util.go").write_text(GO_UTIL.replace("a, b int) int { return a + b",
                                                                 "a, b, c int) int { return a + b + c"))
        self.sh(r, "git", "add", "internal/util/util.go")
        reason = self.denied(self.commit(r, "git commit -m sig"))
        self.assertIn("cmd/app/main.go", reason)
        self.assertIn("not in the changed files", reason)

    @unittest.skipUnless(HAS_GO, "go tools missing")
    def test_go_old_issue_on_untouched_line_is_ignored(self) -> None:
        r = self.repo({"go.mod": "module example.com/m\n\ngo 1.26\n",
                       "a.go": 'package m\n\nimport "os"\n\nfunc A() {\n\tos.Remove("x")\n}\n'})
        (r / "a.go").write_text((r / "a.go").read_text() + "\nfunc B() int { return 1 }\n")
        self.sh(r, "git", "add", "a.go")
        self.assertEqual(self.denied(self.commit(r, "git commit -m b")), "")
        (r / "a.go").write_text((r / "a.go").read_text() + '\nfunc C() { os.Remove("y") }\n')
        self.sh(r, "git", "add", "a.go")
        self.assertIn("errcheck", self.denied(self.commit(r, "git commit -m c")))

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
    def test_stop_mode_blocks_once_then_accepts(self) -> None:
        r = self.repo({"a.py": "def f(x):\n    return x\n"})
        (r / "a.py").write_text("import os\n\ndef f(x):\n    return x\n")
        edit = {"session_id": "s2", "cwd": str(r), "tool_name": "Edit", "tool_input": {"file_path": str(r / "a.py")}}
        stop = {"session_id": "s2", "cwd": str(r), "permission_mode": "default"}
        self.assertEqual(self.hook("stop", stop), {}, "stop gate is off by default")
        self.hook("edit", edit, check_on="stop")
        out = self.hook("stop", stop, check_on="stop")
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("F401", out["reason"])
        self.assertIn("left unfixed", self.hook("stop", stop, check_on="stop").get("systemMessage", ""))

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_sweep_cli(self) -> None:
        r = self.repo({"a.py": "def f(x):\n    return x\n"})
        (r / "a.py").write_text("import os\n\ndef f(x):\n    return x\n")
        p = subprocess.run([str(BROOM), "sweep", "--check"], cwd=r, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("F401", p.stdout)

    # doctor

    def test_doctor_reports_missing_tools_with_install_commands(self) -> None:
        r = self.go_repo()
        result = self.doctor(r, self.fake_path(keep=("go", "gofmt")))
        status = {i["tool"]: i for i in result["items"]}
        self.assertEqual(status["golangci-lint"]["status"], "missing")
        self.assertIn("golangci-lint", status["golangci-lint"]["fix"])
        self.assertEqual(status["gopls"]["fix"], "go install golang.org/x/tools/gopls@latest")
        self.assertFalse(result["healthy"])

    def test_doctor_flags_a_rustup_proxy_without_its_component(self) -> None:
        r = self.repo({"Cargo.toml": '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
                       "src/main.rs": "fn main() {}\n"})
        fake = "echo \"error: Unknown binary 'rust-analyzer' in official toolchain\" >&2; exit 1"
        ra = next(i for i in self.doctor(r, self.fake_path(fakes={"rust-analyzer": fake}))["items"]
                  if i["tool"] == "rust-analyzer")
        self.assertEqual(ra["status"], "broken")
        self.assertIn("Unknown binary", ra["detail"])
        self.assertEqual(ra["fix"], "rustup component add rust-analyzer")

    def test_doctor_flags_old_typescript_and_a_competing_lsp_plugin(self) -> None:
        r = self.ts_repo()
        env = self.fake_path(fakes={"tsc": "echo 'Version 5.9.3'"})
        self.config_dir({"enabledPlugins": {"typescript-lsp@claude-plugins-official": True, "other@x": True}})
        items = self.doctor(r, env)["items"]
        lsp = next(i for i in items if i["role"] == "lsp")
        self.assertEqual(lsp["status"], "broken")
        self.assertIn("TypeScript 7", lsp["detail"])
        conflict = [i for i in items if i["status"] == "conflict"]
        self.assertEqual([c["fix"] for c in conflict], ["claude plugin disable typescript-lsp@claude-plugins-official"])

    def test_doctor_installs_js_tools_as_devdependencies_with_the_projects_package_manager(self) -> None:
        r = self.ts_repo({"pnpm-lock.yaml": "lockfileVersion: '9.0'\n"})
        result = self.doctor(r, self.fake_path())
        self.assertIn("pnpm add -D oxlint oxlint-tsgolint typescript", result["fix"])
        self.assertEqual(result["configure"], ["broom init .", "pnpm add -D oxfmt"])

    def test_doctor_collapses_a_monorepo_to_its_root(self) -> None:
        pkg = '{"name":"p","private":true}\n'
        r = self.repo({"package.json": pkg, "pnpm-lock.yaml": "", "pnpm-workspace.yaml": "packages: ['packages/*']\n",
                       "packages/a/package.json": pkg, "packages/b/package.json": pkg})
        result = self.doctor(r, self.fake_path())
        self.assertEqual(result["configure"], ["broom init .", "pnpm add -D -w oxfmt"])
        self.assertIn("pnpm add -D -w oxlint", result["fix"])
        self.assertFalse([c for c in result["fix"] + result["configure"] if c.startswith("cd ")], "no per-package installs")
        self.assertEqual(len([i for i in result["items"] if i["status"] == "off"]), 2, "one config, one install")

    def test_init_at_a_monorepo_root_covers_the_packages(self) -> None:
        r = self.repo({"apps/a/package.json": "{}\n", "apps/b/package.json": "{}\n"})
        out = self.cli(r, "init").stdout
        self.assertTrue((r / ".oxfmtrc.json").exists(), out)
        self.assertTrue((r / ".oxlintrc.json").exists(), out)
        formats = [i for i in self.doctor(r, {**self.env, "CLAUDE_CONFIG_DIR": str(self.config_dir())})["items"]
                   if i["role"] == "format"]
        self.assertTrue(formats and all(i["status"] != "off" for i in formats), formats)

    # setup offered by the session hook

    def test_session_offers_setup_once_per_session_until_dismissed(self) -> None:
        r = self.go_repo()
        env = self.fake_path(keep=("go", "gofmt"))
        note = self.session(r, "a", env)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("/broom:setup", note)
        self.assertIn("golangci-lint missing", note)
        self.assertEqual(self.session(r, "a", env), {}, "once per session")
        self.assertIn("hookSpecificOutput", self.session(r, "b", env), "a new session hears it again")
        self.assertEqual(self.cli(r, "setup", "--dismiss", env=env).returncode, 0)
        self.assertEqual(self.session(r, "c", env), {}, "dismissed")

    def test_session_asks_again_when_the_gaps_change(self) -> None:
        r = self.repo({"pyproject.toml": "[project]\nname = 'x'\n", "a.py": "x = 1\n"})
        env = self.fake_path(keep=("ruff", "pyright-langserver"))
        self.assertIn("formatting is off", str(self.session(r, "a", env)))
        self.cli(r, "setup", "--done", env=env)
        self.assertEqual(self.session(r, "b", env), {})
        (r / "go.mod").write_text("module example.com/m\n\ngo 1.26\n")
        self.assertIn("golangci-lint missing", str(self.session(r, "c", env)))

    @unittest.skipUnless(HAS_GOPLS, "go tools missing")
    def test_session_is_quiet_and_fast_when_healthy(self) -> None:
        r = self.go_repo()
        env = {**self.env, "CLAUDE_CONFIG_DIR": str(self.config_dir())}
        self.assertEqual(self.session(r, "a", env), {})
        start = time.time()
        self.assertEqual(self.session(r, "b", env), {})
        self.assertLess(time.time() - start, 1.0, "the cached doctor keeps SessionStart fast")
        self.assertEqual(self.session(self.repo({"README.md": "hi\n"}), "c", env), {}, "no languages, nothing to say")

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_missing_tools_never_block_a_commit(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_BAD)
        self.sh(r, "git", "add", "src/main.ts")
        env = self.fake_path()
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Bash", "tool_use_id": "t1",
                   "tool_input": {"command": "git commit -m x"}}
        p = subprocess.run([str(BROOM), "hook", "commit"], input=json.dumps(payload), capture_output=True, text=True,
                           env=env)
        out = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", out)
        self.assertIn("/broom:setup", out["additionalContext"])

    def test_init_adds_only_what_is_missing_and_is_idempotent(self) -> None:
        g = self.go_repo()
        (g / ".golangci.yml").write_text('version: "2"\n')
        self.assertIn("already has", self.cli(g, "init").stdout)
        self.assertEqual((g / ".golangci.yml").read_text(), 'version: "2"\n')
        t = self.ts_repo()
        first = self.cli(t, "init").stdout
        self.assertIn(".oxlintrc.json", first)
        self.assertIn(".oxfmtrc.json", first)
        self.assertIn("already has", self.cli(t, "init").stdout)

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
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        listed = self.cli(r, "known").stdout
        self.assertIn("no-floating-promises", listed)
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

    # per-repo .broom.json

    @unittest.skipUnless(HAS_PY, "ruff missing")
    def test_repo_file_overrides_the_user_settings(self) -> None:
        old = "a = {  'x':1 }\n"
        r = self.repo({"ruff.toml": "", "m.py": old, ".broom.json": '{"format_scope": "file"}'})
        (r / "m.py").write_text(old + "b = {  'y':2 }\n")
        cfg = self.config_dir({"pluginConfigs": {"broom@claude-code-broom": {"options": {"format_scope": "changed"}}}})
        self.cli(r, "fmt", env={**self.env, "CLAUDE_CONFIG_DIR": str(cfg)})
        self.assertEqual((r / "m.py").read_text(), 'a = {"x": 1}\nb = {"y": 2}\n')

    @unittest.skipUnless(HAS_GO, "go tools missing")
    def test_repo_file_can_switch_on_the_edit_hook(self) -> None:
        r = self.repo({"go.mod": "module example.com/m\n\ngo 1.26\n", ".broom.json": '{"format_on": "edit"}'})
        f = r / "z.go"
        f.write_text("package m\nfunc  Z( ) {  }\n")
        payload = {"session_id": "s1", "cwd": str(r), "tool_name": "Write", "tool_input": {"file_path": str(f)}}
        self.hook("edit", payload, cwd=r)
        self.assertEqual(f.read_text(), "package m\n\nfunc Z() {}\n", "the early exit steps aside for .broom.json")

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_excluded_paths_stay_out_of_commits_and_sweeps(self) -> None:
        r = self.ts_repo({".broom.json": '{"exclude": ["src/gen/**"]}'})
        (r / "src/gen").mkdir()
        (r / "src/gen/x.ts").write_text(TS_BAD)
        self.sh(r, "git", "add", "-A")
        self.assertEqual(self.denied(self.commit(r, "git commit -m gen")), "")
        self.assertNotIn("gen/x.ts", self.cli(r, "sweep", "--all").stdout)

    def test_doctor_reports_a_broken_repo_file(self) -> None:
        r = self.repo({".broom.json": '{"check_on": "sometimes", "colour": 1}', "a.py": "x = 1\n"})
        item = next(i for i in self.doctor(r, self.fake_path())["items"] if i["tool"] == ".broom.json")
        self.assertEqual(item["status"], "broken")
        self.assertIn("'sometimes' is not one of", item["detail"])
        self.assertIn("colour", item["detail"])


if __name__ == "__main__":
    unittest.main()
