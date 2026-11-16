"""The commit hook: reading Bash commands for commits, and checking TypeScript and Go commits."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

from support import (
    GO_UTIL, HAS_GO, HAS_TS, ROOT, TS_BAD, TS_MAIN, BroomCase,
)

from broom.gitcmd import GitOp, parse, parse_commit


class CommitTest(BroomCase):
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

    def test_parse_follows_variables_the_command_sets(self) -> None:
        repo = (self.tmp / "r").resolve()
        cwd = lambda command: [str(op.cwd) for op in parse(command, self.tmp)]  # noqa: E731
        self.assertEqual(cwd(f"T={repo}; git -C $T commit -m x"), [str(repo)])
        self.assertEqual(cwd(f"export T={repo} && cd $T && git commit -m x"), [str(repo)])
        self.assertEqual(cwd(f"T={repo} && git -C ${{T}}/sub commit"), [str(repo / "sub")])
        self.assertEqual(cwd(f'D="{repo} b"; git -C "$D" commit'), [f"{repo} b"])
        self.assertEqual(cwd(f"git -c k=v -C {repo} commit -m x"), [str(repo)])
        # Set for one command only: the shell expands $T before the assignment, so it is not the repo.
        self.assertNotEqual(cwd(f"T={repo} git -C $T commit"), [str(repo)])

    def commit_sh(self, repo: Path, command: str) -> dict:
        """The commit hook the way Claude Code runs it: through hooks/commit.sh, for every Bash call."""
        payload = {"session_id": "s1", "cwd": str(repo), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": command}, "tool_use_id": uuid.uuid4().hex}
        r = subprocess.run([str(ROOT / "hooks" / "commit.sh")], input=json.dumps(payload), capture_output=True,
                           text=True, env=self.env, cwd=repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def test_every_bash_call_reaches_the_commit_hook_and_most_leave_at_once(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"]
        self.assertEqual([h.get("if") for m in hooks for h in m["hooks"]], [None], "no if: Claude Code can't match "
                         "`T=…; git -C $T commit`")
        r = self.repo({"a.txt": "x\n"})
        for command in ("ls -la", "npm test", "git log --grep commit", "echo git commit"):
            self.assertEqual(self.commit_sh(r, command), {}, command)

    @unittest.skipUnless(HAS_GO, "go tools missing")
    def test_commits_through_variables_or_git_options_are_checked(self) -> None:
        for n, form in enumerate(("T={r}; git -C $T commit -m x", "git -c commit.gpgsign=false -C {r} commit -m x")):
            r = self.repo({"go.mod": "module example.com/m\n\ngo 1.26\n", "a.go": "package m\n"})
            (r / "a.go").write_text(f'package m\n\nimport "os"\n\nfunc A{n}() {{ os.Remove("x") }}\n')
            self.sh(r, "git", "add", "a.go")
            self.assertIn("errcheck", self.denied(self.commit_sh(r, form.format(r=r))), form)

    # commit hook: TypeScript

    @unittest.skipUnless(HAS_TS, "oxlint/tsc missing")
    def test_commit_denied_then_passes_once_accepted_with_a_reason(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_BAD)
        self.sh(r, "git", "add", "src/main.ts")
        reason = self.denied(self.commit(r, "git commit -m wip"))
        self.assertIn("no-floating-promises", reason)
        self.assertIn("no-unused-vars", reason)
        self.assertIn("no-floating-promises", self.denied(self.commit(r, "git commit -m wip")), "the same result: no")
        self.assertIn("accepted 2 issue(s)", self.cli(r, "known", "--accept", "demo code").stdout)
        self.assertEqual(self.denied(self.commit(r, "git commit -m wip")), "")
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
    def test_type_errors_pass_only_when_accepted_with_a_reason(self) -> None:
        r = self.ts_repo()
        (r / "src/main.ts").write_text(TS_MAIN.replace("fetchIt(1)", 'fetchIt("1")'))
        self.sh(r, "git", "add", "src/main.ts")
        first = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("broom known --accept", first)
        self.assertIn("TS2345", self.denied(self.commit(r, "git commit -m x")), "a retry alone doesn't pass")
        self.assertNotEqual(self.cli(r, "known", "--accept", " ").returncode, 0, "a reason is required")
        accepted = self.cli(r, "known", "--accept", "fetchIt takes strings upstream")
        self.assertIn("accepted 1 issue(s)", accepted.stdout)
        self.assertEqual(self.denied(self.commit(r, "git commit -m x")), "")
        self.assertIn("(fetchIt takes strings upstream)", self.cli(r, "known").stdout)
        self.assertEqual(self.cli(r, "known", "--accept", "again").returncode, 1, "nothing left to accept")

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
