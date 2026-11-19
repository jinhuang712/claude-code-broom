"""`broom doctor --checks`: which checks run in a repo, which don't for lack of a tool, and what needs none."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from support import BroomCase  # first: it puts broom on the path
from broom.gate import display

ROW_KEYS = {"language", "check", "status", "tool", "why", "fix"}
BARE_HEADER = "With no tool installed, broom still checks:"
BARE_CHECKS = {"file length", "function and class length", "nested ternaries", "import and folder cycles",
               "skipped tests", "code files with no test by name"}  # in `checks` beside the rows of the blocks
PY_TOOLS = {"ruff": 'echo "ruff 0.9.0"', "pyright-langserver": "exit 0", "jscpd": 'echo "5.4.0"'}
TS_TOOLS = {name: f'echo "{name} 1.0.0"' for name in ("oxlint", "oxfmt", "tsc", "node", "jscpd", "tsgolint")}
TS_TOOLS.update({"typescript-language-server": "exit 0", "dependency-cruiser": 'echo "16.0.0"'})


class ProtectionTest(BroomCase):
    def checks(self, repo: Path, env: dict) -> dict:
        """The `checks` of `broom doctor --json`, by (language, check)."""
        return {(r["language"], r["check"]): r for r in self.doctor(repo, env)["checks"]}

    def block(self, rows: dict, lang: str) -> dict:
        """The rows of a language's block: its check to its row, without the checks that need no tool."""
        return {check: row for (language, check), row in rows.items() if language == lang and check not in BARE_CHECKS}

    def text(self, repo: Path, env: dict) -> str:
        """What `broom doctor --checks` prints."""
        return self.cli(repo, "doctor", "--checks", env=env).stdout

    def line(self, text: str, mark: str, check: str) -> str:
        """The line of `text` that starts with `mark` and `check`."""
        return next(row.strip() for row in text.splitlines() if row.strip().startswith(f"{mark} {check}"))

    def py_repo(self, *, configured: bool = True) -> Path:
        pyproject = "[project]\nname = 'x'\n" + ("\n[tool.ruff]\nline-length = 100\n" if configured else "")
        return self.repo({"pyproject.toml": pyproject, "a.py": "x = 1\n"})

    def ts_repo_with_formatter(self) -> Path:
        return self.ts_repo({".oxfmtrc.json": "{}\n"})

    # Python

    def test_python_with_ruff_every_check_is_on_or_told_why_not(self) -> None:
        r = self.py_repo()
        env = self.fake_path(fakes=PY_TOOLS)
        rows = self.checks(r, env)
        on = {check: (row["status"], row["tool"]) for check, row in self.block(rows, "py").items()}
        self.assertEqual(on, {
            "format": ("on", "ruff format"), "lint": ("on", "ruff"),
            "type check": ("none", ""), "smells": ("on", "ruff, read by broom"),
            "duplicate and dead code": ("on", "jscpd"), "cycles": ("on", "read by broom"),
            "diagnostics as Claude edits": ("on", "pyright-langserver")})
        self.assertIn("pyright", rows["py", "type check"]["why"], "the absence says what stands in for it")
        text = self.text(r, env)
        self.assertTrue(text.startswith(f"broom doctor --checks: {display(r)}\n"), text)
        self.assertEqual(self.line(text, "✓", "lint").split(), ["✓", "lint", "ruff"])
        self.assertIn("–", self.line(text, "–", "type check"))
        self.assertIn("pyright", self.line(text, "–", "type check"))

    def test_python_without_ruff_the_lint_row_has_the_install_command(self) -> None:
        r = self.py_repo()
        rows = self.checks(r, self.fake_path(fakes={k: v for k, v in PY_TOOLS.items() if k != "ruff"}))
        lint = rows["py", "lint"]
        self.assertEqual((lint["status"], lint["tool"], lint["fix"]), ("off", "ruff", "brew install ruff"))
        self.assertIn("ruff is not installed", lint["why"])
        self.assertEqual(rows["py", "format"]["status"], "off", "ruff formats too")
        self.assertIn("Python isn't formatted", rows["py", "format"]["why"])
        self.assertIn("complexity", rows["py", "smells"]["why"])
        self.assertEqual(rows["py", "duplicate and dead code"]["status"], "on", "jscpd is there")
        self.assertEqual(rows["py", "cycles"]["status"], "on", "broom reads the imports itself")
        text = self.text(r, self.fake_path(fakes={"jscpd": 'echo "5.4.0"'}))
        self.assertIn("ruff is not installed  brew install ruff", self.line(text, "✗", "lint"))

    def test_python_formatting_that_is_off_says_the_config_to_add(self) -> None:
        r = self.py_repo(configured=False)
        fmt = self.checks(r, self.fake_path(fakes=PY_TOOLS))["py", "format"]
        self.assertEqual((fmt["status"], fmt["fix"]), ("off", "broom init ."))
        self.assertIn("no ruff config", fmt["why"])

    # TS/JS

    def test_ts_with_its_tools_every_check_is_on(self) -> None:
        rows = self.checks(self.ts_repo_with_formatter(), self.fake_path(fakes=TS_TOOLS))
        self.assertEqual({check: row["status"] for check, row in self.block(rows, "js").items()},
                         dict.fromkeys(("format", "lint", "type check", "smells", "duplicate and dead code", "cycles",
                                        "diagnostics as Claude edits"), "on"))
        self.assertEqual(rows["js", "type check"]["tool"], "tsc")
        self.assertEqual(rows["js", "format"]["tool"], "oxfmt")
        self.assertIn("dependency-cruiser", rows["js", "cycles"]["tool"])

    def test_ts_without_oxlint_the_lint_smells_and_cycles_rows_are_off(self) -> None:
        r = self.ts_repo_with_formatter()
        rows = self.checks(r, self.fake_path(fakes={k: v for k, v in TS_TOOLS.items() if k != "oxlint"}))
        self.assertEqual(rows["js", "lint"]["fix"], "npm i -D oxlint")
        self.assertIn("TS/JS smells aren't measured", rows["js", "smells"]["why"])
        self.assertEqual(rows["js", "smells"]["fix"], "npm i -g oxlint")
        self.assertIn("import cycles aren't found", rows["js", "cycles"]["why"])
        self.assertEqual(rows["js", "format"]["status"], "on", "the formatter is another tool")

    def test_ts_without_a_formatter_config_the_format_row_gives_both_commands(self) -> None:
        tools = {k: v for k, v in TS_TOOLS.items() if k != "oxfmt"}
        fmt = self.checks(self.ts_repo(), self.fake_path(fakes=tools))["js", "format"]
        self.assertEqual((fmt["status"], fmt["fix"]), ("off", "broom init . && npm i -D oxfmt"))
        self.assertIn("no formatter config", fmt["why"])

    def test_a_missing_type_aware_linter_is_said_of_the_lint_row_only(self) -> None:
        tools = {k: v for k, v in TS_TOOLS.items() if k != "tsgolint"}
        rows = self.checks(self.ts_repo_with_formatter(), self.fake_path(fakes=tools))
        lint = rows["js", "lint"]
        self.assertEqual((lint["status"], lint["tool"], lint["fix"]), ("off", "tsgolint", "npm i -D oxlint-tsgolint"))
        self.assertIn("type-aware rules", lint["why"])

    def test_ts_with_no_tsconfig_has_no_type_check_and_says_so(self) -> None:
        r = self.repo({"package.json": "{}\n", "a.js": "export const a = 1;\n"})
        row = self.checks(r, self.fake_path(fakes=TS_TOOLS))["js", "type check"]
        self.assertEqual((row["status"], row["tool"], row["fix"]), ("none", "", ""))
        self.assertIn("tsconfig.json", row["why"])

    def test_a_biome_that_only_formats_stops_the_format_row_alone(self) -> None:
        r = self.repo({"package.json": "{}\n", "biome.json": '{"linter": {"enabled": false}}\n',
                       "a.js": "export const a = 1;\n"})
        rows = self.checks(r, self.fake_path(fakes=TS_TOOLS))
        self.assertEqual((rows["js", "format"]["status"], rows["js", "format"]["fix"]), ("off", "npm install"))
        self.assertIn("biome", rows["js", "format"]["why"])
        self.assertEqual((rows["js", "lint"]["status"], rows["js", "lint"]["tool"]), ("on", "oxlint"))

    # CSS

    def test_css_has_no_smell_tool_and_the_row_says_so(self) -> None:
        r = self.repo({"a.css": "a { color: red; }\n"})
        env = self.fake_path(fakes={"jscpd": 'echo "5.4.0"', "stylelint": 'echo "16.0.0"'})
        rows = self.checks(r, env)
        self.assertEqual(set(self.block(rows, "css")),
                         {"format", "lint", "smells", "duplicate and dead code", "diagnostics as Claude edits"},
                         "no type check and no cycles for CSS: nothing to say")
        self.assertEqual(rows["css", "smells"]["status"], "none")
        self.assertIn("no smell tool", rows["css", "smells"]["why"])
        self.assertEqual(rows["css", "duplicate and dead code"]["tool"], "jscpd (duplicates only)")
        self.assertEqual(rows["css", "lint"]["status"], "on")
        text = self.text(r, env)
        self.assertIn("no smell tool for CSS", self.line(text, "–", "smells"))
        self.assertIn("vscode-langservers-extracted", self.line(text, "✗", "diagnostics as Claude edits"))

    def test_scss_is_a_block_of_its_own_and_its_lint_needs_the_dialect_config(self) -> None:
        r = self.repo({"package.json": "{}\n", "a.scss": "a { b { color: red; } }\n"})
        rows = self.checks(r, self.fake_path(fakes={"stylelint": 'echo "16.0.0"'}))
        lint = rows["scss", "lint"]
        self.assertEqual(lint["status"], "off")
        self.assertEqual(lint["fix"], "npm i -D stylelint-config-recommended-scss")
        self.assertEqual(rows["css", "lint"]["status"], "on", "plain CSS has the stylelint it needs")

    # the JSON

    def test_json_gains_the_checks_key_and_keeps_the_others(self) -> None:
        r = self.py_repo()
        env = self.fake_path(fakes=PY_TOOLS)
        result = self.doctor(r, env)
        self.assertEqual(set(result), {"version", "repo", "languages", "items", "fix", "configure", "fix_global",
                                       "configure_global", "healthy", "optional", "settings", "checks"})
        self.assertTrue(result["checks"])
        for row in result["checks"]:
            self.assertEqual(set(row), ROW_KEYS)
            self.assertIn(row["status"], ("on", "off", "none"))
            if row["status"] != "off":
                self.assertEqual((row["fix"]), "", row)
        both = self.cli(r, "doctor", "--checks", "--json", env=env).stdout
        self.assertEqual(json.loads(both), result, "--checks --json prints what --json does")

    def test_json_rows_of_what_needs_no_tool_are_in_the_checks_too(self) -> None:
        rows = self.checks(self.py_repo(), self.fake_path())
        self.assertEqual(rows["py", "file length"]["tool"], "read by broom")
        self.assertEqual(rows["any", "broom stats: sizes, tests, rot, history"]["status"], "on")
        self.assertNotIn(("js", "file length"), rows, "only the languages the repo has")

    # what needs no tool

    def test_the_last_block_lists_what_needs_no_tool_for_the_repos_languages(self) -> None:
        r = self.repo({"pyproject.toml": "", "a.py": "x = 1\n", "main.go": "package main\n", "go.mod": "module m\n"})
        text = self.text(r, self.fake_path())
        head, _, tail = text.partition(BARE_HEADER)
        self.assertTrue(tail, text)
        self.assertIn("✗ lint", head, "with no tool at all the rows above are off")
        rows = dict(re.match(r"\s*✓ (.+?)\s{2,}(.+)$", row).groups() for row in tail.strip().splitlines())
        self.assertEqual(rows["file length"], "Go, Python")
        self.assertEqual(rows["function and class length"], "Python")
        self.assertEqual(rows["import and folder cycles"], "Python")
        self.assertEqual(rows["skipped tests"], "Go, Python")
        self.assertEqual(rows["code files with no test by name"], "Go, Python")
        self.assertEqual(rows["broom stats: sizes, tests, rot, history"], "every language")
        self.assertEqual(text.splitlines()[-1].split()[-2:], ["every", "language"], "it is the last block")

    def test_with_smells_off_the_smell_rows_say_so_and_the_scan_checks_leave_the_last_block(self) -> None:
        r = self.py_repo()
        (r / ".broom.json").write_text('{"smells": "off"}\n')
        env = self.fake_path(fakes=PY_TOOLS)
        rows = self.checks(r, env)
        for check in ("smells", "duplicate and dead code", "cycles"):
            self.assertEqual((rows["py", check]["status"], rows["py", check]["why"]),
                             ("none", "the smells setting is off"), check)
        self.assertEqual(rows["py", "lint"]["status"], "on", "linting is not a smell")
        self.assertNotIn(("py", "file length"), rows)
        self.assertIn(("any", "broom stats: sizes, tests, rot, history"), rows)

    def test_a_repo_with_no_code_has_no_language_block(self) -> None:
        text = self.text(self.repo({"README.md": "hi\n"}), self.fake_path())
        self.assertIn("Languages: none found", text)
        self.assertIn(BARE_HEADER, text)
        self.assertNotIn("file length", text)

    # nothing more is started, and the doctor is as it was

    def test_the_plain_doctor_asks_for_the_oxlint_of_the_smells_where_eslint_lints(self) -> None:
        r = self.ts_repo({".oxfmtrc.json": "{}\n", "eslint.config.js": "export default [];\n"})
        tools = {k: v for k, v in TS_TOOLS.items() if k != "oxlint"}
        result = self.doctor(r, self.fake_path(fakes={**tools, "eslint": 'echo "9.0.0"'}))
        gaps = {(i["lang"], i["role"], i["tool"]): i for i in result["items"] if i["status"] != "ok"}
        self.assertIn(("js", "smells", "oxlint"), gaps, "the smell scan needs it whichever linter lints")
        self.assertNotIn(("js", "lint", "oxlint"), gaps, "eslint is the project's linter")
        self.assertFalse(result["healthy"])

    def test_the_plain_doctor_sees_a_css_formatter_missing_outside_a_js_project(self) -> None:
        r = self.repo({"a.css": "a { color: red; }\n", ".prettierrc": "{}\n"})
        result = self.doctor(r, self.fake_path())
        css = [i for i in result["items"] if i["lang"] == "css" and i["tool"] == "prettier"]
        self.assertTrue(css and css[0]["status"] != "ok", result["items"])

    def test_smells_turned_off_one_by_one_are_named_after_the_languages(self) -> None:
        r = self.repo({"a.py": "x = 1\n", ".broom.json": '{"smells_off": ["magic_numbers", "todo"]}\n'})
        text = self.text(r, self.fake_path(fakes=PY_TOOLS))
        self.assertIn("turned off in .broom.json: magic_numbers, todo", self.line(text, "–", "smells off"))
        self.assertGreater(text.index("smells off"), text.index("Beside the languages:"))

    def test_the_checks_start_no_tool_the_plain_doctor_does_not(self) -> None:
        r = self.py_repo()
        log = self.tmp / "started.log"
        logged = {name: f"echo {name} \"$@\" >> {shlex.quote(str(log))}; {body}" for name, body in PY_TOOLS.items()}
        env = self.fake_path(fakes=logged)
        self.cli(r, "doctor", env=env)
        plain = sorted(log.read_text().splitlines())
        log.write_text("")
        self.assertEqual(self.cli(r, "doctor", "--checks", env=env).returncode, 1)
        self.assertEqual(sorted(log.read_text().splitlines()), plain)
        self.assertTrue(plain, "the fake tools were started by the doctor itself")

    def test_the_plain_doctor_prints_no_protection_list_and_the_exit_codes_agree(self) -> None:
        r = self.py_repo()
        env = self.fake_path(fakes=PY_TOOLS)
        plain = self.cli(r, "doctor", env=env)
        self.assertTrue(plain.stdout.startswith("broom doctor: "), plain.stdout)
        self.assertNotIn(BARE_HEADER, plain.stdout)
        self.assertEqual(plain.returncode, 1, "git's hook is missing")
        self.assertEqual(self.cli(r, "doctor", "--checks", env=env).returncode, 1)
        listed = self.cli(r, "doctor", "--checks", env=env).stdout
        self.assertIn("Beside the languages:", listed, "a gap that is no check of a language fails the doctor too")
        self.assertRegex(listed, r"✗ git hook +commits Claude Code's commit hook doesn't see go unchecked  broom install-hook")
        self.assertEqual(self.cli(r, "install-hook", env=env).returncode, 0)
        self.assertNotIn("Beside the languages:", self.cli(r, "doctor", "--checks", env=env).stdout)
        plain = self.cli(r, "doctor", env=env)
        self.assertEqual(plain.returncode, 0, plain.stdout)
        self.assertIn("All set.", plain.stdout)
        self.assertEqual(self.cli(r, "doctor", "--checks", env=env).returncode, 0, "the same as the plain doctor's")
        self.assertEqual(self.cli(r, "doctor", "--checks", "--json", env=env).returncode, 0)
