"""Goal O11, no open finding is forgotten (F2.14): a finding that no check has ended is told to Claude again at the
prompt after a question and at a session's start, its file checked again first; an idle prompt and an idle session
start tell nothing and check nothing."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

from support import ROOT
from test_asked import AskedCase, rows, six

from broom import comeback, ledger

PROMPT_SH = ROOT / "hooks" / "prompt.sh"
FEWER = "def second(a, b):\n    return a + b\n"  # the second function, fixed by hand: 2 parameters


def context(out: dict) -> str:
    return out.get("hookSpecificOutput", {}).get("additionalContext", "")


class ComebackCase(AskedCase):
    def prompt(self, r: Path, shell: tuple = ()) -> subprocess.CompletedProcess:
        """A prompt's synchronous hook, as Claude Code runs it: hooks/prompt.sh, under `shell` when one is given."""
        return subprocess.run([*shell, str(PROMPT_SH)], input=json.dumps({"session_id": "s1", "cwd": str(r), "prompt": "yes"}),
                              capture_output=True, text=True, env=self.env, cwd=r)

    def told(self, r: Path) -> str:
        out = self.prompt(r)
        self.assertEqual((out.returncode, out.stderr.strip()), (0, ""))
        return context(json.loads(out.stdout)) if out.stdout.strip() else ""

    def session_told(self, r: Path, session: str) -> str:
        return context(self.session(r, session, self.env, event="session-scan"))


class AcceptanceTest(ComebackCase):
    def test_two_findings_put_to_the_user_are_told_at_the_next_prompt_and_at_a_new_session_until_fixed(self) -> None:
        r = self.blocked_commit(six("first", "second"))
        self.assertEqual(self.ask(r).returncode, 0)
        self.assertIn("2 findings WAIT FOR YOUR ANSWER", self.stop(r)["systemMessage"])
        told = self.told(r)
        self.assertIn("about 2 findings still open: a.py:1 params, a.py:5 params", told)
        self.assertIn("may stock keep 6 parameters?", told)
        self.assertIn('`broom known --accept "<why>" --agreed`', told)
        self.assertEqual(self.hook("prompt", {"session_id": "s1", "cwd": str(r)}), {}, "both still there")
        self.assertEqual(self.told(r), "", "told once")
        self.assertEqual(rows("fix"), [])

        news = self.session_told(r, "s2")
        self.assertIn("broom: 2 findings that stopped a commit or a turn's end are still open in this repo, 2 of them "
                      "put to the user: a.py:1 params (asked), a.py:5 params (asked).", news)

        (r / "a.py").write_text(six("first") + "\n\n" + FEWER)  # the second fixed by hand, no hook saw it
        news = self.session_told(r, "s3")
        self.assertIn("broom: 1 finding that stopped a commit or a turn's end is still open in this repo, 1 of them "
                      "put to the user: a.py:1 params (asked).", news)
        self.assertNotIn("a.py:5", news)
        (fix,) = rows("fix")
        second = [b for b in rows("block") if b["line"] == 5][0]
        self.assertEqual((fix["key"], fix["file"], fix["rule"]), (second["key"], "a.py", "params"))
        data = json.loads(self.cli(r, "report", "--json").stdout)
        self.assertEqual((data["fixed"], data["open"]), (1, 1), "the record holds it as fixed")


class MomentsTest(ComebackCase):
    def test_a_finding_fixed_before_the_prompt_is_not_told_and_the_async_hook_says_what_it_found_gone(self) -> None:
        r = self.blocked_commit(six("first", "second"))
        self.assertEqual(self.ask(r).returncode, 0)
        self.stop(r)
        self.assertIn("about 2 findings", self.told(r))
        (r / "a.py").write_text(six("first") + "\n\n" + FEWER)
        out = context(self.hook("prompt", {"session_id": "s1", "cwd": str(r)}))
        self.assertEqual(out, "broom: 1 of the findings you asked the user about is gone now, recorded as fixed or no "
                              "longer checked: a.py:5 params. Nothing to do for it.")
        self.assertEqual(len(rows("fix")), 1)

    def test_a_finding_whose_file_is_gone_leaves_with_no_line_and_is_not_told(self) -> None:
        r = self.blocked_commit()
        self.assertEqual(self.ask(r).returncode, 0)
        self.stop(r)
        (r / "a.py").unlink()
        self.assertEqual(self.told(r).count("a.py"), 1, "the record still holds it: the prompt tells it")
        self.assertNotIn("still open", self.session_told(r, "s2"))
        self.assertEqual(rows("fix"), [])

    def test_an_accepted_finding_is_not_told(self) -> None:
        r = self.blocked_commit()
        self.assertEqual(self.ask(r).returncode, 0)
        self.stop(r)
        self.assertEqual(self.cli(r, "known", "--accept", "the user said keep it", "--agreed").returncode, 0)
        self.assertEqual(self.told(r), "")
        self.assertNotIn("still open", self.session_told(r, "s2"))

    def test_a_finding_never_asked_about_is_told_at_a_session_start_but_not_at_a_prompt(self) -> None:
        r = self.blocked_commit()
        self.assertEqual(self.told(r), "")
        self.assertIn("1 finding that stopped a commit or a turn's end is still open in this repo: a.py:1 params.",
                      self.session_told(r, "s2"))

    def test_a_long_list_names_five_and_counts_the_rest(self) -> None:
        r = self.blocked_commit(six(*[f"f{i}" for i in range(7)]))
        self.assertIn("7 findings that stopped", self.session_told(r, "s2"))
        self.assertIn(", and 2 more.", self.session_told(r, "s3"))


class IdleTest(ComebackCase):
    def test_an_idle_prompt_leaves_before_python_starts_and_tells_nothing(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        out = self.prompt(r, ("sh", "-x"))
        self.assertEqual((out.returncode, out.stdout), (0, ""))
        self.assertNotIn("bin/broom", out.stderr, "no question waits: no interpreter starts")
        _git, loaded = self.counted("prompt", {"session_id": "s1", "cwd": str(r)}, r)
        self.assertNotIn("broom.comeback", loaded, "the async prompt hook checks nothing again")

    def test_an_idle_session_start_tells_nothing_and_checks_nothing(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        other = self.blocked_commit()  # open findings in another repo are no part of this one
        with mock.patch.object(comeback, "found_now", side_effect=AssertionError("checked")):
            self.assertIsNone(comeback.session_note(r))
        self.assertTrue(comeback.standing(str(other)))
        self.assertNotIn("still open", self.session_told(r, "s2"))

    def test_the_record_of_one_repo_is_read_without_parsing_the_others(self) -> None:
        ledger.write([ledger.line("block", "/elsewhere", key="k1", tool="ruff", rule="E1", file="a.py")])
        with mock.patch.object(ledger.json, "loads", side_effect=AssertionError("parsed")):
            self.assertEqual(comeback.standing("/here"), {})
