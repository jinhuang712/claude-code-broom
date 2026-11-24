"""The limits card: the bar told to Claude at session start, from the repo's own numbers."""

from __future__ import annotations

import json
from pathlib import Path

from support import CARD, BroomCase

BAR = (
    "broom's bar in this repo, for the code you write or touch: functions up to 50 lines (hard limit 100), files up "
    "to 400 (1000), test files up to 800 (2000), parameters up to 5 (8), nesting up to 4 (6), complexity up to 10 "
    "(20). A length counts code lines: comment lines and blank lines are free. A change is also blocked "
    "when it adds a lint suppression without a reason, a swallowed error or commented-out code. A commit and a "
    "turn's end stop on code past the first number, as on most smells a change adds, until it is fixed or accepted "
    'with `broom known --accept "<why>"`: trying again passes nothing. If the user must decide, `broom known --ask '
    '"<question>"` and stop. Code already past its hard limit can\'t grow. '
    "Run the project's tests after your last change to code: where a repo has tests, a turn's end stops without that. "
    "For a repo's numbers ask broom before writing a script: "
    "`broom stats` (lines, tests, coverage, suppressions, TODOs, what changes most), `broom smells` (smells, ranked; "
    "`--only function_lines` for the longest functions), `broom diagnose` (the whole repo: with those, dead code, "
    "missing doc comments, calls to deprecated APIs, duplicate tests and unused dependencies), `broom report` (what "
    "was blocked, fixed and let through), `broom doctor` (tools)."
)


class LimitsCardTest(BroomCase):
    def py_repo(self, config: dict = None) -> Path:
        extra = {".broom.json": json.dumps(config)} if config is not None else {}
        return self.repo({"pyproject.toml": "[project]\nname = 'x'\n", "a.py": "x = 1\n", **extra})

    def card(self, r: Path, session: str = "s1") -> str:
        out = self.session(r, session, self.fake_path())
        text = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        return next((x for x in text.split("\n\n") if x.startswith(CARD)), "")

    def test_the_card_gives_the_bar_the_repo_holds_code_to_and_needs_no_tool(self) -> None:
        self.assertEqual(self.card(self.py_repo()), BAR, "the PATH holds only git and python3")

    def test_the_card_comes_once_per_session_and_before_the_other_notes(self) -> None:
        r = self.py_repo()
        env = self.fake_path()
        text = self.session(r, "s1", env)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(text.startswith(BAR + "\n\n"), "before the offer of setup")
        self.assertIn("/broom:setup", text)
        self.assertEqual(self.session(r, "s1", env), {}, "once per session")
        self.assertEqual(self.card(r, "s2"), BAR, "a new session hears it again")

    def test_the_card_alone_is_what_a_repo_with_nothing_else_to_say_hears(self) -> None:
        r = self.py_repo()
        env = self.fake_path()
        self.assertEqual(self.cli(r, "setup", "--dismiss", env=env).returncode, 0)
        self.assertEqual(self.session(r, "s1", env),
                         {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": BAR}})

    def test_the_cards_numbers_are_the_repos_own(self) -> None:
        r = self.py_repo({"limits": {"function_lines": [30, 60], "file_lines": [200, 500], "params": [3, 6]}})
        card = self.card(r)
        self.assertIn("functions up to 30 lines (hard limit 60), files up to 200 (500), test files up to 400 (1000), "
                      "parameters up to 3 (6), nesting up to 4 (6), complexity up to 10 (20).", card)

    def test_the_card_names_a_limit_that_differs_for_test_files(self) -> None:
        r = self.py_repo({"test_limits": {"function_lines": [300, 600]}})
        self.assertIn("functions up to 50 lines (hard limit 100), test functions up to 300 lines (600), files up to "
                      "400 (1000), test files up to 800 (2000), parameters", self.card(r),
                      "tests' limits aren't the bar for code, and each is said beside it")
        r = self.py_repo({"test_limits": {"file_lines": [400, 1000]}})
        self.assertIn("files up to 400 (1000), parameters", self.card(r), "a repo that holds its tests to the code's")
        r = self.py_repo({"smells_off": ["file_lines"]})
        self.assertNotIn("files up to", self.card(r), "a smell turned off is left out for tests too")

    def test_a_smell_the_repo_turned_off_is_left_out(self) -> None:
        r = self.py_repo({"smells_off": ["function_lines", "complexity", "commented_code"]})
        card = self.card(r)
        self.assertIn("files up to 400 (hard limit 1000), test files up to 800 (2000), parameters up to 5 (8), nesting up to 4 "
                      "(6).", card)
        self.assertNotIn("functions up to", card)
        self.assertNotIn("complexity", card)
        self.assertIn("adds a lint suppression without a reason or a swallowed error.", card)
        self.assertNotIn("commented-out", card)
        self.assertIn("A length counts code lines", card, "a file's length is still named")
        r = self.py_repo({"smells_off": ["suppression", "swallowed_error", "commented_code"]})
        self.assertNotIn("A change is also blocked", self.card(r))
        r = self.py_repo({"smells_off": ["function_lines", "file_lines"]})
        self.assertNotIn("A length counts", self.card(r), "no length is named, so what one counts isn't said")

    def test_no_card_without_a_language_or_with_smells_off(self) -> None:
        env = self.fake_path()
        self.assertEqual(self.session(self.repo({"README.md": "hi\n"}), "s1", env), {}, "no language")
        r = self.py_repo({"smells": "off"})
        self.assertEqual(self.card(r), "", "smells are off")
