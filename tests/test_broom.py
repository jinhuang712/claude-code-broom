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
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BROOM = ROOT / "bin" / "broom"
sys.path.insert(0, str(ROOT / "lib"))

from broom.gitcmd import GitOp, parse, parse_commit  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
HAS_GO = all(shutil.which(t) for t in ("go", "gofmt", "golangci-lint"))
HAS_TS = all(shutil.which(t) for t in ("oxlint", "tsc"))
HAS_PY = shutil.which("ruff") is not None

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

    def hook(self, event: str, payload: dict, **options: str) -> dict:
        env = {**self.env, **{f"CLAUDE_PLUGIN_OPTION_{k.upper()}": v for k, v in options.items()}}
        r = subprocess.run([str(BROOM), "hook", event], input=json.dumps(payload), capture_output=True, text=True,
                           env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr.strip(), "", "hook raised")
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def commit(self, repo: Path, command: str, tool_use_id: str = None, **options: str) -> dict:
        return self.hook("commit", {"session_id": "s1", "cwd": str(repo), "hook_event_name": "PreToolUse",
                                    "tool_name": "Bash", "tool_input": {"command": command},
                                    "tool_use_id": tool_use_id or uuid.uuid4().hex}, **options)

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


if __name__ == "__main__":
    unittest.main()
