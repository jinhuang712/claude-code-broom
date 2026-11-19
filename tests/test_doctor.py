"""The doctor, the setup the session hook offers, and the repo's .broom.json."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from support import (
    BROOM, HAS_GO, HAS_PY, HAS_TS, ROOT, TS_BAD, BroomCase,
)

from broom import githook
from broom.doctor import cache_key



class DoctorTest(BroomCase):
    # doctor

    def tools(self, r: Path, env: dict) -> dict:
        return {i["tool"]: i for i in self.doctor(r, env)["items"]}

    def test_doctor_asks_for_node_where_broom_s_ts_rules_run_on_it(self) -> None:
        r = self.repo({"package.json": "{}", "a.ts": "export const a = 1;\n"})
        missing = self.tools(r, self.fake_path(fakes={"brew": "exit 0"}))["node"]
        self.assertEqual((missing["status"], missing["fix"]), ("missing", "brew install node"))
        self.assertEqual(self.tools(r, self.fake_path(fakes={"node": "echo v99.0.0"}))["node"]["status"], "ok")
        (r / ".broom.json").write_text('{"smells": "off"}')
        self.assertNotIn("node", self.tools(r, self.fake_path()), "nothing here needs Node once smells are off")

    def test_python_with_no_project_file_is_found_by_its_tracked_files(self) -> None:
        r = self.repo({"tools/sync.py": "print(1)\n", "lib/pkg/pyproject.toml": "", "lib/pkg/a.py": "A = 1\n",
                       "venv/x.py": "X = 1\n"})
        result = self.doctor(r, self.fake_path())
        self.assertEqual(sorted(result["languages"]["py"]), [".", "lib/pkg"],
                         "a script takes the root, a file under a pyproject.toml its folder, and an environment none")
        missing = {i["tool"] for i in result["items"] if i["lang"] == "py" and i["status"] == "missing"}
        self.assertIn("ruff", missing, "a repo of scripts is told its linter is missing")

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

    def test_doctor_flags_a_missing_typescript_server_and_a_competing_lsp_plugin(self) -> None:
        r = self.ts_repo()
        env = self.fake_path(fakes={"tsc": "echo 'Version 5.9.3'"})
        self.config_dir({"enabledPlugins": {"typescript-lsp@claude-plugins-official": True, "other@x": True}})
        items = self.doctor(r, env)["items"]
        lsp = next(i for i in items if i["role"] == "lsp")
        self.assertEqual((lsp["tool"], lsp["status"]), ("typescript-language-server", "missing"))
        self.assertIn("no typescript-language-server and no TypeScript 7 (global tsc: 5.9.3)", lsp["detail"])
        self.assertEqual((lsp["fix"], lsp["global_fix"]), (self.own_install(),) * 2)
        conflict = [i for i in items if i["status"] == "conflict"]
        self.assertEqual([c["fix"] for c in conflict], ["claude plugin disable typescript-lsp@claude-plugins-official"])

    def test_the_launcher_becomes_the_chosen_server(self) -> None:
        r = self.ts_install("5.9.3")
        env = self.fake_path(fakes={"typescript-language-server": 'echo "tls $*"', "tsc": "echo 'Version 7.0.2'"})
        p = self.cli(r, "lsp", "typescript", env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "tls --stdio", "the server has the process: stdin and stdout are its")
        self.assertIn("the project's TypeScript 5.9.3, through typescript-language-server", p.stderr)
        lsp = json.loads((ROOT / ".lsp.json").read_text())["typescript"]
        self.assertEqual([lsp["command"], *lsp["args"]], ["${CLAUDE_PLUGIN_ROOT}/bin/broom", "lsp", "typescript"],
                         "Claude Code expands CLAUDE_PLUGIN_ROOT; the plugin's bin/ isn't on the server's PATH")

    def test_doctor_asks_for_typescript_language_server_when_only_typescript_7_would_serve(self) -> None:
        r = self.ts_install("5.9.3", {"tsconfig.json": "{}\n", "src/a.ts": "export {}\n"})
        items = self.doctor(r, self.fake_path(fakes={"tsc": "echo 'Version 7.0.2'"}))["items"]
        lsp = next(i for i in items if i["role"] == "lsp")
        self.assertEqual((lsp["tool"], lsp["status"]), ("typescript-language-server", "missing"))
        self.assertIn("without it the language server is the global TypeScript 7.0.2", lsp["detail"])
        self.assertIn("no diagnostics", lsp["detail"])
        self.assertEqual((lsp["fix"], lsp["global_fix"]), (self.own_install(),) * 2)

    def test_doctor_says_missing_with_broom_s_own_install_when_the_path_server_cannot_start(self) -> None:
        r = self.ts_install("7.0.1", {"tsconfig.json": "{}\n", "src/a.ts": "export {}\n"})
        env = self.npm_server(self.fake_path(), "7.0.2")
        lsp = next(i for i in self.doctor(r, env)["items"] if i["role"] == "lsp")
        self.assertEqual((lsp["tool"], lsp["status"]), ("typescript-language-server", "missing"))
        self.assertEqual((lsp["fix"], lsp["global_fix"]), (self.own_install(),) * 2)
        self.assertIn("which has no tsserver", lsp["detail"])

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

    @unittest.skipUnless(shutil.which("oxfmt"), "oxfmt missing")
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
        self.assertEqual(self.noted(self.session(r, "c", env)), "", "dismissed")

    def test_session_asks_again_when_the_gaps_change(self) -> None:
        r = self.repo({"pyproject.toml": "[project]\nname = 'x'\n", "a.py": "x = 1\n"})
        env = self.fake_path(keep=("ruff", "pyright-langserver"))
        self.assertIn("formatting is off", str(self.session(r, "a", env)))
        self.cli(r, "setup", "--done", env=env)
        self.assertEqual(self.noted(self.session(r, "b", env)), "")
        (r / "go.mod").write_text("module example.com/m\n\ngo 1.26\n")
        self.assertIn("golangci-lint missing", str(self.session(r, "c", env)))

    def test_setup_answers_hold_in_every_repo(self) -> None:
        env = self.fake_path(keep=("go", "gofmt"))
        a, b = self.go_repo(), self.go_repo()
        self.assertIn("golangci-lint missing", str(self.session(a, "s", env)))
        self.cli(a, "setup", "--dismiss", env=env)
        self.assertEqual(self.noted(self.session(b, "s2", env)), "", "the same kinds of gap, answered in another repo")
        items = self.doctor(b, env)["items"]
        self.assertTrue(all(i["answered"] for i in items if i["status"] != "ok"), items)
        py = self.repo({"go.mod": "module example.com/m\n\ngo 1.26\n", "pyproject.toml": "[project]\nname = 'x'\n"})
        note = str(self.session(py, "s3", env))
        self.assertIn("ruff missing", note, "a new kind of gap is raised")
        self.assertNotIn("golangci-lint", note, "only the new kinds")
        self.assertIn("forgot", self.cli(a, "setup", "--reset", env=env).stdout)
        self.assertIn("golangci-lint missing", str(self.session(b, "s4", env)), "reset asks again")

    def test_doctor_reports_settings_and_global_installs(self) -> None:
        r = self.ts_repo()
        env = self.fake_path(fakes={"npm": "exit 0"})
        env["CLAUDE_CONFIG_DIR"] = str(self.config_dir({"pluginConfigs": {"broom@claude-code-broom": {
            "options": {"check_on": "stop"}}}}))
        (r / ".broom.json").write_text('{"format_scope": "file"}\n')
        out = self.doctor(r, env)
        self.assertEqual(out["settings"], {"format_on": {"value": "edit", "source": "default"},
                                           "check_on": {"value": "stop", "source": "user"},
                                           "format_scope": {"value": "file", "source": "repo"},
                                           "smells": {"value": "on", "source": "default"}})
        self.assertTrue(any(c.startswith("npm i -D") for c in out["fix"]), out["fix"])
        self.assertIn("npm i -g oxlint", out["fix_global"])
        self.assertFalse(any("npm i -D" in c for c in out["fix_global"] + out["configure_global"]), out)

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


class DependencyCruiserItemTest(BroomCase):
    """The dependency-cruiser item: ok when one reads this repo's code, else a gap with broom's own copy as the fix."""
    tools = DoctorTest.tools

    def ts_repo_of_one_file(self) -> Path:
        return self.repo({"package.json": "{}", "a.ts": "export const a = 1;\n", "b.js": "export const b = 1;\n"})

    def test_a_blind_copy_on_path_is_a_gap_whose_detail_says_why_and_whose_fix_is_broom_s_copy(self) -> None:
        r = self.ts_repo_of_one_file()
        result = self.doctor(r, self.npm_depcruise(self.fake_path(), "7.0.2"))
        item = {i["tool"]: i for i in result["items"]}["dependency-cruiser"]
        self.assertEqual((item["status"], item["fix"]), ("missing", self.own_install()))
        self.assertIn("the TypeScript beside it is 7.0.2, and it needs one below 7", item["detail"])
        self.assertIn(self.own_install(), result["fix"])
        self.assertIn(self.own_install(), result["fix_global"], "the copy is broom's, global tools or not")
        self.assertFalse(result["healthy"])

    def test_nothing_installed_is_the_same_gap_with_no_reason(self) -> None:
        item = self.tools(self.ts_repo_of_one_file(), self.fake_path())["dependency-cruiser"]
        self.assertEqual((item["status"], item["detail"], item["fix"]), ("missing", "", self.own_install()))

    def test_broom_s_own_copy_or_a_good_one_on_path_is_ok(self) -> None:
        r = self.ts_repo_of_one_file()
        self.assertEqual(self.tools(r, self.npm_depcruise(self.fake_path(), "5.9.3"))["dependency-cruiser"]["status"],
                         "ok")
        self.own_depcruise()
        item = self.tools(r, self.npm_depcruise(self.fake_path(), "7.0.2"))["dependency-cruiser"]
        self.assertEqual((item["status"], item["detail"], item["fix"]), ("ok", "18.8.0", ""))

    def test_a_js_only_repo_takes_the_copy_on_path_whatever_typescript_it_has(self) -> None:
        r = self.repo({"package.json": "{}", "b.js": "export const b = 1;\n"})
        item = self.tools(r, self.npm_depcruise(self.fake_path(), "7.0.2"))["dependency-cruiser"]
        self.assertEqual((item["status"], item["detail"]), ("ok", "18.8.0"))

    def test_installing_the_copy_changes_the_key_of_the_cached_diagnosis(self) -> None:
        r = self.ts_repo_of_one_file()
        before = cache_key(r, {})
        self.own_depcruise()
        self.assertNotEqual(cache_key(r, {}), before)


class SetupOfferTest(BroomCase):
    """What setup offers: git's pre-commit hook with the missing tools, and nothing for a repo that has it all."""

    def hook_items(self, result: dict) -> list:
        return [i for i in result["items"] if i["role"] == "hook"]

    def py_repo(self) -> Path:
        return self.repo({"pyproject.toml": "[project]\nname = 'x'\n", "a.py": "x = 1\n"})

    def test_doctor_offers_gits_hook_until_it_is_installed(self) -> None:
        r = self.py_repo()
        env = self.fake_path(keep=("ruff", "pyright-langserver"))
        result = self.doctor(r, env)
        (hook,) = self.hook_items(result)
        self.assertEqual((hook["lang"], hook["tool"], hook["status"], hook["fix"]),
                         ("git", "pre-commit", "missing", "broom install-hook"))
        self.assertIn("broom install-hook", result["fix"])
        text = self.cli(r, "doctor", env=env)
        self.assertIn("pre-commit", text.stdout)
        self.assertIn("broom install-hook", text.stdout)
        self.assertIn("pre-commit hook", str(self.session(r, "a", env)), "the session offers it with the rest")
        self.assertEqual(self.cli(r, "install-hook", env=env).returncode, 0)
        after = self.doctor(r, env)
        self.assertEqual(self.hook_items(after), [], "gone once the hook is there")
        self.assertNotIn("broom install-hook", after["fix"])
        self.assertNotIn("pre-commit hook", str(self.session(r, "b", env)), "the cached doctor saw it arrive")

    def test_with_another_tools_hook_doctor_says_so_and_gives_the_line_to_add(self) -> None:
        r = self.py_repo()
        env = self.fake_path(keep=("ruff", "pyright-langserver"))
        (r / ".git/hooks/pre-commit").write_text("#!/bin/sh\nexit 0\n")
        result = self.doctor(r, env)
        (hook,) = self.hook_items(result)
        self.assertEqual((hook["status"], hook["fix"]), ("missing", ""), "broom never replaces it")
        self.assertIn("another tool's hook", hook["detail"])
        self.assertIn(githook.LINE, hook["detail"])
        self.assertNotIn("broom install-hook", result["fix"])
        (r / ".git/hooks/pre-commit").write_text(f"#!/bin/sh\n{githook.LINE}\nexit 0\n")
        self.assertEqual(self.hook_items(self.doctor(r, env)), [], "gone once the line is in their hook")

    def test_a_repo_without_code_is_not_offered_gits_hook(self) -> None:
        r = self.repo({"README.md": "hi\n"})
        self.assertEqual(self.hook_items(self.doctor(r, self.fake_path())), [])

    def test_declining_gits_hook_once_holds_in_every_repo(self) -> None:
        env = self.fake_path(keep=("ruff", "pyright-langserver"))
        a, b = self.py_repo(), self.py_repo()
        self.assertIn("pre-commit hook", str(self.session(a, "s", env)))
        self.assertEqual(self.cli(a, "setup", "--dismiss", env=env).returncode, 0)
        self.assertEqual(self.noted(self.session(b, "s2", env)), "", "the same kinds of gap, git's hook among them")
        (hook,) = self.hook_items(self.doctor(b, env))
        self.assertTrue(hook["answered"])
        self.assertEqual(self.hook_items(self.doctor(a, env))[0]["answered"], True)
