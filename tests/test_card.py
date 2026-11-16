"""The limits card: the bar told to Claude at session start, from the repo's own numbers."""

from __future__ import annotations

import json
from pathlib import Path

from support import CARD, BroomCase

BAR = (
    "broom's bar in this repo, for the code you write or touch: functions up to 50 lines (blocked past 100), files up "
    "to 400 (1000), parameters up to 5 (8), nesting up to 4 (6), complexity up to 10 (20). A change is also blocked "
    "when it adds a lint suppression without a reason, a swallowed error or commented-out code. A blocked finding "
    'passes fixed, or with `broom known --accept "<why>"`. For a repo\'s numbers ask broom before writing a script: '
    "`broom stats` (lines, tests, suppressions, TODOs, what changes most), `broom smells` (smells, ranked), "
    "`broom diagnose` (the whole repo, before a refactor), `broom report` (what was blocked, fixed and let through), "
    "`broom doctor` (tools)."
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
        self.assertIn("functions up to 30 lines (blocked past 60), files up to 200 (500), parameters up to 3 (6), "
                      "nesting up to 4 (6), complexity up to 10 (20).", card)
        r = self.py_repo({"test_limits": {"function_lines": [300, 600]}})
        self.assertIn("functions up to 50 lines (blocked past 100)", self.card(r), "tests' limits aren't the bar for code")

    def test_a_smell_the_repo_turned_off_is_left_out(self) -> None:
        r = self.py_repo({"smells_off": ["function_lines", "complexity", "commented_code"]})
        card = self.card(r)
        self.assertIn("files up to 400 (blocked past 1000), parameters up to 5 (8), nesting up to 4 (6).", card)
        self.assertNotIn("functions", card)
        self.assertNotIn("complexity", card)
        self.assertIn("adds a lint suppression without a reason or a swallowed error.", card)
        self.assertNotIn("commented-out", card)
        r = self.py_repo({"smells_off": ["suppression", "swallowed_error", "commented_code"]})
        self.assertNotIn("A change is also blocked", self.card(r))

    def test_no_card_without_a_language_or_with_smells_off(self) -> None:
        env = self.fake_path()
        self.assertEqual(self.session(self.repo({"README.md": "hi\n"}), "s1", env), {}, "no language")
        r = self.py_repo({"smells": "off"})
        self.assertEqual(self.card(r), "", "smells are off")
