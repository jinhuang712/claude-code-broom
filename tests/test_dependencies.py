"""Unused dependencies in `broom diagnose`: knip, deptry, cargo-machete and `go mod tidy -diff`, each parsed from the
output its documentation gives (tests/fixtures/deps) and run by a small script on PATH that logs its directory and
arguments. A tool that is missing is named once with its install command, one that fails is said with its first error
line, and none of them runs in a hook. The doctor lists them as optional, which changes nothing else it says."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import unittest
from pathlib import Path
from typing import List

from support import BROOM, BroomCase

from broom import dependencies as deps

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "deps"
PYPROJECT = '[project]\nname = "x"\nversion = "0"\ndependencies = ["requests"]\n'
CARGO = '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n'
GO_MOD = "module example.com/y\n\ngo 1.22\n\nrequire github.com/google/uuid v1.6.0\n"
GO_FREE = "package main\n\nfunc main() {}\n"
KNIP_ARGS = "--include dependencies --reporter json --no-progress"
GO_VERSION = "if [ \"$1\" = env ]; then echo {version}; exit 0; fi"


def fixture(name: str) -> object:
    """The JSON of a fixture file."""
    return json.loads((FIXTURES / name).read_text())


class ParseTest(unittest.TestCase):
    repo = Path("/r")

    def test_knip_s_json_gives_the_dependencies_and_devdependencies_of_each_package_json(self) -> None:
        rows = deps.knip_rows(self.repo, self.repo, fixture("knip.json"))
        self.assertEqual(rows, [{"project": ".", "unused": ["left-pad", "lodash"], "dev": ["jest"]},
                                {"project": "packages/ui", "unused": ["classnames"], "dev": []}],
                         "a file knip lists besides a package.json (an unused file) is no project")

    def test_a_project_with_nothing_unused_still_has_its_row(self) -> None:
        self.assertEqual(deps.knip_rows(self.repo, self.repo, {"issues": []}),
                         [{"project": ".", "unused": [], "dev": []}])
        self.assertEqual(deps.machete_rows(self.repo, self.repo, {}), [{"project": ".", "unused": [], "dev": []}])
        self.assertEqual(deps.deptry_rows(self.repo, self.repo, []), [{"project": ".", "unused": [], "dev": []}])

    def test_deptry_s_json_counts_only_the_dependencies_nothing_imports(self) -> None:
        self.assertEqual(deps.deptry_rows(self.repo, self.repo, fixture("deptry.json")),
                         [{"project": ".", "unused": ["requests"], "dev": []}], "DEP001 (numpy) is another rule")

    def test_cargo_machete_s_json_gives_the_unused_crates_of_each_manifest(self) -> None:
        rows = deps.machete_rows(self.repo, self.repo, fixture("machete.json"))
        self.assertEqual(rows, [{"project": ".", "unused": ["log"], "dev": []},
                                {"project": "crates/core", "unused": ["anyhow", "serde"], "dev": []}],
                         "`ignored_used` (prost) is not unused")
        absolute = {"crates": [{"manifest_path": "/r/crates/x/Cargo.toml", "unused": ["rand"]}]}
        self.assertIn({"project": "crates/x", "unused": ["rand"], "dev": []},
                      deps.machete_rows(self.repo, self.repo, absolute), "a manifest path may be absolute")

    def test_go_mod_tidy_s_diff_gives_the_direct_requirements_it_would_drop(self) -> None:
        rows = deps.tidy_rows(self.repo, self.repo, (FIXTURES / "go-tidy.diff").read_text())
        self.assertEqual(rows, [{"project": ".", "unused": ["github.com/google/uuid", "golang.org/x/text"], "dev": []}],
                         "not the `// indirect` one, and not the go.sum lines")

    def test_the_first_line_of_an_error_is_the_stderr_s_else_the_stdout_s(self) -> None:
        self.assertEqual(deps.first_line("out line", "\n  err line\nmore"), "err line")
        self.assertEqual(deps.first_line("out line\nmore", ""), "out line")
        self.assertEqual(deps.first_line("", ""), "no output")


class DependencyCase(BroomCase):
    def setUp(self) -> None:
        super().setUp()
        self.log = self.tmp / "calls.log"

    def fake(self, name: str, rc: int = 1, err: str = "") -> str:
        """The body of a tool that logs where it ran and with what, prints a fixture and exits with `rc`."""
        said = f"printf '%s\\n' {shlex.quote(err)} >&2\n" if err else ""
        return f'echo "$(pwd -P) $*" >> {self.log}\n{said}cat {FIXTURES / name}\nexit {rc}'

    def fake_deptry(self, rc: int = 1) -> str:
        """deptry writes its JSON to the file `--json-output` names."""
        return (f'echo "$(pwd -P) $*" >> {self.log}\nwhile [ $# -gt 0 ]; do\n'
                f'  if [ "$1" = --json-output ]; then cp {FIXTURES / "deptry.json"} "$2"; fi\n  shift\ndone\nexit {rc}')

    def calls(self) -> List[str]:
        """What the fake tools logged, a line per call."""
        return self.log.read_text().splitlines() if self.log.exists() else []

    def tools(self, **fakes: str) -> dict:
        """An environment with only git, python3, cat, cp, touch and the fake tools on PATH."""
        return self.fake_path(keep=("cat", "cp", "touch"), fakes=fakes)

    def dependencies(self, repo: Path, env: dict, *args: str) -> dict:
        done = self.cli(repo, "diagnose", "--json", *args, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["dependencies"]


class RunTest(DependencyCase):
    def test_knip_runs_in_the_project_for_dependencies_only_and_its_json_is_read(self) -> None:
        r = self.repo({"package.json": '{"name": "x"}\n', "a.js": "export const a = 1;\n"})
        data = self.dependencies(r, self.tools(knip=self.fake("knip.json")))
        self.assertEqual(self.calls(), [f"{r} {KNIP_ARGS}"])
        found = {(p["project"], tuple(p["unused"]), tuple(p["dev"])) for p in data["projects"]}
        self.assertEqual(found, {(".", ("left-pad", "lodash"), ("jest",)), ("packages/ui", ("classnames",), ())})
        self.assertEqual({(p["ecosystem"], p["tool"], p["status"]) for p in data["projects"]}, {("js", "knip", "ok")})

    def test_a_workspace_is_read_by_knip_from_its_root_alone(self) -> None:
        r = self.repo({"package.json": '{"name": "x", "workspaces": ["packages/*"]}\n',
                       "packages/ui/package.json": '{"name": "ui"}\n', "packages/api/package.json": '{"name": "a"}\n'})
        self.dependencies(r, self.tools(knip=self.fake("knip.json")))
        self.assertEqual(self.calls(), [f"{r} {KNIP_ARGS}"], "once: knip reads each workspace from the root")

    def test_deptry_runs_in_the_project_for_unused_dependencies_and_its_file_is_read(self) -> None:
        r = self.repo({"pyproject.toml": PYPROJECT, "src/main.py": "X = 1\n"})
        data = self.dependencies(r, self.tools(deptry=self.fake_deptry()))
        (call,) = self.calls()
        self.assertRegex(call, rf"^{r} \. --json-output \S+deptry\.json --no-ansi --ignore DEP001,DEP003,DEP004,DEP005$")
        self.assertEqual([(p["ecosystem"], p["tool"], p["project"], p["unused"]) for p in data["projects"]],
                         [("py", "deptry", ".", ["requests"])])

    def test_the_projects_own_deptry_goes_before_the_one_on_path(self) -> None:
        r = self.repo({"pyproject.toml": PYPROJECT})
        own = r / ".venv/bin/deptry"
        own.parent.mkdir(parents=True)
        own.write_text("#!/bin/sh\n" + self.fake_deptry().replace(str(self.log), f"{self.log}.venv"))
        own.chmod(0o755)
        self.dependencies(r, self.tools(deptry=self.fake_deptry()))
        self.assertFalse(self.log.exists(), "the one on PATH was not started")
        self.assertTrue(Path(f"{self.log}.venv").exists(), "the virtualenv's was: it has the project's package metadata")

    def test_cargo_machete_runs_through_cargo_and_gives_the_crates_by_manifest(self) -> None:
        r = self.repo({"Cargo.toml": CARGO, "crates/core/Cargo.toml": CARGO})
        data = self.dependencies(r, self.tools(cargo=self.fake("machete.json"), **{"cargo-machete": "exit 0"}))
        self.assertEqual(self.calls(), [f"{r} machete --json ."], "once, from the top: it reads every crate below")
        self.assertEqual([(p["project"], p["unused"]) for p in data["projects"]],
                         [(".", ["log"]), ("crates/core", ["anyhow", "serde"])])

    def test_go_mod_tidy_runs_without_the_network_and_gives_the_direct_requirements(self) -> None:
        r = self.repo({"go.mod": GO_MOD, "main.go": GO_FREE})
        go = GO_VERSION.format(version="go1.27.1") + "\n" + self.fake("go-tidy.diff").replace('$*', '$* GOPROXY=$GOPROXY')
        data = self.dependencies(r, self.tools(go=go))
        self.assertEqual(self.calls(), [f"{r} mod tidy -diff GOPROXY=off"])
        self.assertEqual([(p["ecosystem"], p["tool"], p["unused"]) for p in data["projects"]],
                         [("go", "go mod tidy -diff", ["github.com/google/uuid", "golang.org/x/text"])])

    @unittest.skipUnless(shutil.which("go"), "go missing")
    def test_the_real_go_tidies_offline(self) -> None:
        version = subprocess.run(["go", "env", "GOVERSION"], capture_output=True, text=True).stdout.strip()
        major, minor = (int(n) for n in version.removeprefix("go").split(".")[:2])
        if (major, minor) < deps.GO_TIDY_DIFF:
            self.skipTest(f"{version} has no `go mod tidy -diff`")
        r = self.repo({"go.mod": "module example.com/z\n\ngo 1.22\n\nrequire example.invalid/none v1.0.0\n",
                       "main.go": GO_FREE})
        data = self.dependencies(r, self.fake_path(keep=("go",)))
        self.assertEqual([(p["status"], p["unused"]) for p in data["projects"]], [("ok", ["example.invalid/none"])])

    def test_a_go_older_than_1_23_is_named_with_its_version(self) -> None:
        r = self.repo({"go.mod": GO_MOD, "main.go": GO_FREE})
        data = self.dependencies(r, self.tools(go=GO_VERSION.format(version="go1.22.1") + "\nexit 9"))
        self.assertEqual(data["projects"], [])
        self.assertEqual(data["not_measured"], [{"ecosystem": "go", "tool": "go mod tidy -diff", "install": "",
                                                 "reason": "`go mod tidy -diff` needs Go 1.23 or later, and this is "
                                                           "go1.22.1"}])

    def test_a_project_the_repo_excludes_is_left_out(self) -> None:
        r = self.repo({"package.json": "{}\n", "fixtures/a/package.json": "{}\n",
                       ".broom.json": '{"exclude": ["fixtures/**"]}'})
        self.dependencies(r, self.tools(knip=self.fake("knip.json")))
        self.assertEqual(self.calls(), [f"{r} {KNIP_ARGS}"])

    def test_a_diagnosis_narrowed_to_paths_takes_the_projects_that_overlap_them(self) -> None:
        r = self.repo({"web/package.json": "{}\n", "api/package.json": "{}\n"})
        self.dependencies(r, self.tools(knip=self.fake("knip.json")), "web/src", "api")
        self.assertEqual(sorted(self.calls()), sorted([f"{r / 'web'} {KNIP_ARGS}", f"{r / 'api'} {KNIP_ARGS}"]))
        self.log.unlink()
        self.dependencies(r, self.tools(knip=self.fake("knip.json")), "api")
        self.assertEqual(self.calls(), [f"{r / 'api'} {KNIP_ARGS}"])


class MissingAndFailingTest(DependencyCase):
    def test_a_tool_that_is_not_installed_is_named_once_with_its_install_command(self) -> None:
        r = self.repo({"a/package.json": "{}\n", "b/package.json": "{}\n", "pyproject.toml": PYPROJECT,
                       "Cargo.toml": CARGO, "go.mod": GO_MOD})
        data = self.dependencies(r, self.fake_path())
        self.assertEqual(data["projects"], [])
        self.assertEqual([(m["ecosystem"], m["reason"], m["install"]) for m in data["not_measured"]],
                         [("js", "knip is not installed", "npm i -g knip"),
                          ("py", "deptry is not installed", "uv tool install deptry"),
                          ("rust", "cargo-machete is not installed", "cargo install cargo-machete"),
                          ("go", "go is not installed", "brew install go")], "knip once, for two packages")
        text = self.cli(r, "diagnose", env=self.fake_path()).stdout
        self.assertEqual(text.count("not measured: knip is not installed (`npm i -g knip`)"), 1)
        self.assertIn("not measured: deptry is not installed (`uv tool install deptry`)", text)
        self.assertIn("not measured: cargo-machete is not installed (`cargo install cargo-machete`)", text)

    def test_cargo_machete_needs_cargo_beside_it(self) -> None:
        r = self.repo({"Cargo.toml": CARGO})
        data = self.dependencies(r, self.tools(**{"cargo-machete": "exit 0"}))
        self.assertEqual([m["tool"] for m in data["not_measured"] if m["ecosystem"] == "rust"], ["cargo-machete"])

    def test_a_tool_that_fails_is_said_with_its_first_error_line(self) -> None:
        r = self.repo({"package.json": "{}\n", "pyproject.toml": PYPROJECT})
        broken = self.fake("knip.json", rc=2, err="Error: Cannot load config\nat load (knip.js:1)").replace(
            f"cat {FIXTURES / 'knip.json'}\n", "")
        data = self.dependencies(r, self.tools(knip=broken, deptry="echo 'Traceback (most recent call last)' >&2\nexit 1"))
        failed = {p["tool"]: p for p in data["projects"]}
        self.assertEqual((failed["knip"]["status"], failed["knip"]["error"], failed["knip"]["unused"]),
                         ("failed", "Error: Cannot load config", []))
        self.assertEqual((failed["deptry"]["status"], failed["deptry"]["error"]),
                         ("failed", "Traceback (most recent call last)"), "exit 1 with no report is an error")
        text = self.cli(r, "diagnose", env=self.tools(knip=broken)).stdout
        self.assertIn("knip failed: Error: Cannot load config", text)

    def test_output_that_is_not_json_is_a_failure_too(self) -> None:
        r = self.repo({"package.json": "{}\n"})
        data = self.dependencies(r, self.tools(knip="echo 'knip needs Node 20' \nexit 0"))
        self.assertEqual([(p["status"], p["error"]) for p in data["projects"]], [("failed", "knip needs Node 20")])

    def test_go_that_cannot_reach_a_module_says_why_and_that_broom_uses_no_network(self) -> None:
        r = self.repo({"go.mod": GO_MOD, "main.go": GO_FREE})
        err = "go: example.com/y imports x: module lookup disabled by GOPROXY=off"
        go = GO_VERSION.format(version="go1.27.1") + f"\nprintf '%s\\n' {shlex.quote(err)} >&2\nexit 1"
        (row,) = self.dependencies(r, self.tools(go=go))["projects"]
        self.assertEqual(row["status"], "failed")
        self.assertTrue(row["error"].startswith("go: example.com/y imports x: module lookup disabled"), row["error"])
        self.assertTrue(row["error"].endswith("`go mod download` fetches what the module cache lacks)"), row["error"])


class ReportTest(DependencyCase):
    def test_the_section_comes_after_the_check_up_with_a_table_of_the_projects(self) -> None:
        r = self.repo({"package.json": "{}\n", "pyproject.toml": PYPROJECT})
        text = self.cli(r, "diagnose", env=self.tools(knip=self.fake("knip.json"), deptry=self.fake_deptry())).stdout
        self.assertLess(text.index("## Check-up"), text.index("## Dependencies"))
        self.assertLess(text.index("## Dependencies"), text.index("## Size"))
        section = text.split("## Dependencies\n")[1].split("\n\n## ")[0].splitlines()
        self.assertRegex(section[0], r"^  language\s+project\s+tool\s+unused packages$")
        self.assertRegex(section[1], r"^  TS/JS\s+\.\s+knip\s+left-pad, lodash; dev: jest$")
        self.assertRegex(section[2], r"^  TS/JS\s+packages/ui\s+knip\s+classnames$")
        self.assertRegex(section[3], r"^  Python\s+\.\s+deptry\s+requests$")

    def test_a_clean_project_says_none_and_a_repo_with_no_project_says_so(self) -> None:
        r = self.repo({"package.json": "{}\n"})
        text = self.cli(r, "diagnose", env=self.tools(knip="echo '{\"issues\": []}'\nexit 0")).stdout
        self.assertRegex(text, r"\n  TS/JS\s+\.\s+knip\s+none\n")
        bare = self.cli(self.repo({"README.md": "x\n"}), "diagnose", env=self.fake_path()).stdout
        self.assertIn("## Dependencies\n  no project found: no package.json, pyproject.toml, requirements.txt, "
                      "Cargo.toml or go.mod\n", bare)


class NoHookTest(DependencyCase):
    MARK = "touch {mark}\nexit 0"

    def test_no_hook_starts_any_of_them_and_diagnose_does(self) -> None:
        mark = self.tmp / "ran"
        fakes = {name: self.MARK.format(mark=mark) for name in ("knip", "deptry", "cargo-machete")}
        r = self.repo({"package.json": "{}\n", "pyproject.toml": PYPROJECT, "Cargo.toml": CARGO, "a.py": "X = 1\n"})
        env = self.tools(**fakes)
        self.session(r, "s1", env)
        self.session(r, "s1", env, "session-scan")
        (r / "a.py").write_text("X = 2\n")
        self.sh(r, "git", "add", "a.py")
        payload = {"session_id": "s1", "cwd": str(r), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "git commit -m x"}, "tool_use_id": "t1"}
        hook = subprocess.run([str(BROOM), "hook", "commit"], input=json.dumps(payload), capture_output=True, text=True,
                              env=env, cwd=r)
        self.assertEqual((hook.returncode, hook.stderr), (0, ""))
        self.assertFalse(mark.exists(), "a hook started one of them")
        self.assertEqual(self.cli(r, "diagnose", env=env).returncode, 0)
        self.assertTrue(mark.exists(), "diagnose didn't, and it is the one place that does")


class DoctorTest(DependencyCase):
    def doctor_of(self, repo: Path, env: dict) -> tuple[subprocess.CompletedProcess, dict]:
        done = self.cli(repo, "doctor", "--json", env=env)
        return done, json.loads(done.stdout)

    def test_the_optional_tools_are_listed_with_their_install_commands(self) -> None:
        r = self.repo({"package.json": "{}\n", "pyproject.toml": PYPROJECT, "Cargo.toml": CARGO})
        _, bare = self.doctor_of(r, self.fake_path())
        self.assertEqual([(t["tool"], t["installed"], t["install"]) for t in bare["optional"]],
                         [("knip", False, "npm i -g knip"), ("deptry", False, "uv tool install deptry"),
                          ("cargo-machete", False, "cargo install cargo-machete"),
                          ("osv-scanner", False, "brew install osv-scanner")])
        _, some = self.doctor_of(r, self.fake_path(fakes={"knip": "exit 0"}))
        self.assertEqual([t["installed"] for t in some["optional"]], [True, False, False, False])
        text = self.cli(r, "doctor", env=self.fake_path()).stdout
        self.assertIn("Optional, for `broom diagnose`", text)
        self.assertIn("○ knip           unused dependencies in TS/JS  install: npm i -g knip", text)

    def test_only_the_languages_a_repo_has_get_their_tool(self) -> None:
        _, d = self.doctor_of(self.repo({"go.mod": GO_MOD, "main.go": GO_FREE}), self.fake_path())
        self.assertEqual([t["tool"] for t in d["optional"]], ["osv-scanner"],
                         "none of the unused-dependency tools serves Go: `go mod tidy -diff` needs no install")
        _, none = self.doctor_of(self.repo({"README.md": "x\n"}), self.fake_path())
        self.assertEqual(none["optional"], [])
        self.assertNotIn("Optional", self.cli(self.repo({"README.md": "x\n"}), "doctor", env=self.fake_path()).stdout)

    def test_they_are_no_gap_no_fix_and_no_part_of_the_exit_code(self) -> None:
        r = self.repo({"package.json": "{}\n", "pyproject.toml": PYPROJECT, "Cargo.toml": CARGO})
        with_tools = self.fake_path(fakes={"knip": "exit 0", "deptry": "exit 0", "cargo-machete": "exit 0",
                                           "osv-scanner": "exit 0"})
        bare_done, bare = self.doctor_of(r, self.fake_path())
        done, d = self.doctor_of(r, with_tools)
        self.assertEqual(bare_done.returncode, done.returncode)
        for key in ("items", "fix", "configure", "fix_global", "configure_global", "healthy", "languages"):
            self.assertEqual(bare[key], d[key], f"{key} is the same with or without them")
        self.assertNotIn("knip", json.dumps([bare["items"], bare["fix"], bare["configure"]]))
        self.assertFalse(any("deptry" in c for c in bare["fix"] + bare["fix_global"]))

    def test_a_healthy_repo_stays_healthy_and_exits_0_with_every_optional_tool_missing(self) -> None:
        r = self.repo({"pyproject.toml": PYPROJECT + "\n[tool.ruff]\nline-length = 100\n", "a.py": "X = 1\n"})
        env = self.fake_path(fakes={"ruff": "echo ruff 0.15.0", "pyright-langserver": "exit 0", "jscpd": "echo 5.0.0"})
        self.assertEqual(self.cli(r, "install-hook", env=env).returncode, 0)
        done, d = self.doctor_of(r, env)
        deptry = [t["installed"] for t in d["optional"] if t["tool"] == "deptry"]
        self.assertEqual((done.returncode, d["healthy"], deptry), (0, True, [False]))
        self.assertIn("All set.", self.cli(r, "doctor", env=env).stdout)

    def test_they_are_never_raised_at_session_start(self) -> None:
        r = self.repo({"pyproject.toml": PYPROJECT + "\n[tool.ruff]\nline-length = 100\n", "a.py": "X = 1\n"})
        env = self.fake_path(fakes={"ruff": "echo ruff 0.15.0", "pyright-langserver": "exit 0", "jscpd": "echo 5.0.0"})
        self.cli(r, "install-hook", env=env)
        out = self.session(r, "s1", env)
        self.assertEqual(self.noted(out), "", "no gap, so nothing is raised: not setup, not the tools")
        self.assertNotIn("deptry", json.dumps(out))
