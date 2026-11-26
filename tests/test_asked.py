"""Goal R5, a pass is told to the user: Claude asks the user with `broom known --ask` and stops, which ends the turn
with the question put and passes nothing; the user's yes is marked with `--agreed`; a block says which block it is; and
a turn that accepted many on its own says so loudly."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from support import py_function
from test_nowave import NoWaveCase, passes

from broom import ledger

ASKED_LINE = "broom: 1 finding WAITS FOR YOUR ANSWER: a.py:1 params: may stock keep 6 parameters?"
QUESTION = "may stock keep 6 parameters?"
SIX = "def stock(a, b, c, d, e, f):\n    return a + b + c + d + e + f\n"  # one parameter past the limit


def six(*names: str) -> str:
    """One function with 6 parameters for each name: each is a finding of its own, none a copy of another."""
    return "\n\n".join(f"def {n}(a, b, c, d, e, f):\n    return a + b + c + d + e + f + {i}\n"
                       for i, n in enumerate(names))


def rows(event: str) -> list:
    """The ledger lines of one event."""
    return [r for r in ledger.read(ledger.LEDGER) if r["event"] == event]


class AskedCase(NoWaveCase):
    def blocked_commit(self, text: str = SIX) -> Path:
        """A repo where the turn edited a.py and a commit of it was denied."""
        r = self.repo({"a.py": "x = 1\n"})
        self.staged(r, text)
        self.edit(r)
        self.assertIn("params", self.denied(self.commit(r, "git commit -m x")))
        return r

    def ask(self, r: Path, question: str = QUESTION):
        return self.cli(r, "known", "--ask", question)

    def touch(self, r: Path, name: str, text: str) -> None:
        """Write `text` to `name` and tell broom the turn edited it."""
        (r / name).write_text(text)
        self.hook("edit", {"session_id": "s1", "cwd": str(r), "tool_name": "Edit",
                           "tool_input": {"file_path": str(r / name)}})

    def next_turn(self, r: Path) -> None:
        """A new prompt and an edit of a.py: the next turn has something to check."""
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})
        self.edit(r)


class AskTest(AskedCase):
    def test_after_a_commit_denial_asking_and_stopping_ends_the_turn_with_the_question_put(self) -> None:
        r = self.blocked_commit()
        out = self.ask(r)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("1 issue(s) wait for the user's answer", out.stdout)
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE}, "no block: the question is the user's now")
        self.assertEqual(self.stop(r), {}, "the question was put once")
        self.assertIn("stock takes 6 parameters", self.denied(self.commit(r, "git commit -m x")),
                      "the same commit is still denied: nothing passed")
        self.assertEqual(self.cli(r, "known").stdout.strip(), "broom: no known issues here")

    def test_asking_writes_an_ask_line_and_no_pass_and_the_report_counts_it_open_and_against_the_rate(self) -> None:
        r = self.blocked_commit()
        self.assertEqual(self.ask(r).returncode, 0)
        (block,) = rows("block")
        (ask,) = rows("ask")
        self.assertEqual((ask["key"], ask["why"], ask["rule"], ask["file"], ask["where"]),
                         (block["key"], QUESTION, "params", "a.py", "commit"))
        self.assertEqual(passes(), [], "asking lets nothing through")
        data = json.loads(self.cli(r, "report", "--json").stdout)
        self.assertEqual((data["blocked"], data["open"], data["open_asked"], data["fixed"], data["let_through"],
                          data["asked"], data["fix_rate"]), (1, 1, 1, 0, 0, 1, 0.0), "nothing ended the question")
        text = self.cli(r, "report").stdout
        self.assertIn("still open 1 (asked 1), asked the user 1, fix rate 0%", text)
        row = next(line.split() for line in text.splitlines() if line.strip().startswith("params"))
        self.assertEqual(row[-4:], ["1", "(asked", "1)", "0%"], "the rule's row: open, asked, and its rate")

    def test_a_finding_that_was_asked_about_is_fixed_later_and_the_fix_is_on_record(self) -> None:
        r = self.blocked_commit()
        self.assertEqual(self.ask(r).returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE})
        self.staged(r, py_function("small", 20))
        self.assertEqual(self.commit(r, "git commit -m x"), {})
        data = json.loads(self.cli(r, "report", "--json").stdout)
        self.assertEqual((data["open"], data["open_asked"], data["fixed"], data["asked"], data["fix_rate"]),
                         (0, 0, 1, 1, 1.0), "asked, then fixed")

    def test_the_finding_blocks_again_at_the_end_of_a_next_turn_that_edits_its_file(self) -> None:
        r = self.blocked_commit()
        self.assertEqual(self.ask(r).returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE})
        self.next_turn(r)
        out = self.stop(r)
        self.assertEqual(out.get("decision"), "block", "asked about in the turn before: it blocks like any other")
        self.assertIn("stock takes 6 parameters", out["reason"])
        self.assertIn("Block 1 of 3.", out["reason"])
        self.assertEqual(self.ask(r, "and now?").returncode, 0, "asked about again")
        self.assertEqual(self.stop(r)["systemMessage"], ASKED_LINE.replace(QUESTION, "and now?"))

    def test_a_next_turn_blocks_on_it_only_when_it_changes_its_file(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.touch(r, "a.py", SIX)
        self.assertIn("a.py:1:0  params", self.stop(r)["reason"])
        self.assertEqual(self.ask(r).returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE})
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})
        self.assertEqual(self.stop(r), {}, "a turn that changed nothing checks nothing")
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})
        self.touch(r, "b.py", "y = 2\n")
        self.assertEqual(self.stop(r), {}, "a turn that changed another file doesn't check a.py")
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})
        self.touch(r, "a.py", SIX + "\n")
        self.assertEqual(self.stop(r).get("decision"), "block", "a turn that changed a.py blocks on it")
        self.sh(r, "git", "add", "a.py")
        self.assertIn("stock takes 6 parameters", self.denied(self.commit(r, "git commit -m x")),
                      "and a commit of a.py is denied all along: nothing passed")

    def test_a_finding_not_asked_about_still_blocks_beside_one_that_was(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.touch(r, "a.py", SIX)
        self.assertIn("a.py:1:0  params", self.stop(r)["reason"])
        self.assertEqual(self.ask(r).returncode, 0)
        self.touch(r, "b.py", six("other"))
        out = self.stop(r)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("b.py:1:0  params", out["reason"], "what wasn't asked about blocks")
        self.assertNotIn("a.py:1", out["reason"], "what was asked about doesn't")
        self.assertIn("Block 2 of 3.", out["reason"])
        self.touch(r, "b.py", "y = 2\n")
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE}, "the question still stands at the end")
        out = self.cli(r, "known", "--accept", "the user said keep it", "--agreed")
        self.assertEqual(out.returncode, 0, "the answer can be accepted in the next turn without a new block")
        self.assertIn("accepted 1 issue(s)", out.stdout)

    def test_a_turn_that_gives_up_on_the_rest_tells_the_question_first(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.touch(r, "a.py", SIX)
        self.assertEqual(self.stop(r).get("decision"), "block")
        self.assertEqual(self.ask(r).returncode, 0)
        self.touch(r, "b.py", six("other"))
        for _ in range(2):
            self.assertEqual(self.stop(r).get("decision"), "block")
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE + "; broom GAVE UP after 3 blocks: 1 finding(s) "
                                        "left unfixed and unaccepted: b.py:1 params; broom let 1 through this turn: "
                                        "1 params (gave-up)"})
        self.assertEqual([(x["file"], x["how"]) for x in rows("pass")], [("b.py", "gave-up")], "a.py was asked, not let go")

    def test_a_turn_end_block_that_was_asked_about_keeps_its_fix_line_for_the_next_turn(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.touch(r, "a.py", SIX)
        self.assertEqual(self.stop(r).get("decision"), "block")
        self.assertEqual(self.ask(r).returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE})
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})
        self.touch(r, "a.py", "x = 2\n")
        self.assertEqual(self.stop(r), {})
        self.assertEqual([x["file"] for x in rows("fix")], ["a.py"], "fixed after the question, and it says so")

    def test_the_question_is_told_when_the_turn_changed_no_code(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.staged(r, SIX)
        self.assertIn("params", self.denied(self.commit(r, "git commit -m x")))
        self.assertEqual(self.ask(r).returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE}, "no edit of this turn was recorded")

    def test_a_question_is_for_the_turn_it_was_asked_in(self) -> None:
        r = self.blocked_commit()
        self.assertEqual(self.ask(r).returncode, 0)
        self.hook("prompt", {"session_id": "s1", "cwd": str(r)})
        self.assertEqual(self.stop(r).get("decision"), "block", "a new prompt began a turn: the question didn't carry")

    def test_a_block_of_gits_own_hook_is_put_to_the_user_in_the_session_broom_runs_in(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.assertEqual(self.cli(r, "install-hook").returncode, 0)
        self.staged(r, SIX)
        self.edit(r)
        out = subprocess.run(["git", "commit", "-qm", "x"], cwd=r, env=self.env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 1, out.stderr)
        out = self.cli(r, "known", "--ask", QUESTION, env={**self.env, "CLAUDE_CODE_SESSION_ID": "s1"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE}, "the hook has no turn: the session's is used")

    def test_asking_works_where_accepting_is_off(self) -> None:
        r = self.blocked_commit()
        self.env["BROOM_NO_ACCEPT"] = "1"
        self.assertEqual(self.cli(r, "known", "--accept", "x").returncode, 1)
        out = self.ask(r)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.stop(r), {"systemMessage": ASKED_LINE})

    def test_asking_with_nothing_blocked_or_no_question_exits_1(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        out = self.ask(r)
        self.assertEqual(out.returncode, 1)
        self.assertIn("no blocked commit or turn end to ask about", out.stdout)
        self.assertEqual(rows("ask"), [])
        r = self.blocked_commit()
        out = self.ask(r, "  ")
        self.assertEqual(out.returncode, 1)
        self.assertIn("say what the user must decide", out.stderr)
        self.assertEqual(rows("ask"), [])

    def test_several_findings_asked_in_one_question_are_named_together(self) -> None:
        r = self.blocked_commit(six("one", "two"))
        self.assertEqual(self.ask(r).returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": "broom: 2 findings WAIT FOR YOUR ANSWER: a.py:1 params, "
                                                         f"a.py:5 params: {QUESTION}"})


class AgreedTest(AskedCase):
    def test_an_accept_the_user_agreed_to_is_marked_in_the_ledger_and_the_summary(self) -> None:
        r = self.blocked_commit()
        out = self.cli(r, "known", "--accept", "a long signature by design", "--agreed")
        self.assertEqual((out.returncode, out.stdout.strip()),
                         (0, "broom: accepted 1 issue(s) as known (a long signature by design); commit again"))
        (through,) = rows("pass")
        self.assertEqual((through["how"], through["why"], through["agreed"]),
                         ("accept", "a long signature by design", True))
        self.assertEqual(self.stop(r), {"systemMessage": "broom let 1 through this turn: 1 params (accepted, the user "
                                                         "agreed: a long signature by design)"})

    def test_an_accept_on_its_own_has_no_mark(self) -> None:
        r = self.blocked_commit()
        self.assertEqual(self.cli(r, "known", "--accept", "a long signature by design").returncode, 0)
        (through,) = rows("pass")
        self.assertNotIn("agreed", through)
        self.assertEqual(self.stop(r), {"systemMessage": "broom let 1 through this turn: 1 params "
                                                         "(accepted: a long signature by design)"})

    def test_agreed_without_accept_is_an_error(self) -> None:
        r = self.blocked_commit()
        for args in (("--agreed",), ("--ask", QUESTION, "--agreed")):
            out = self.cli(r, "known", *args)
            self.assertEqual(out.returncode, 1, args)
            self.assertIn("--agreed goes with --accept", out.stderr)
        self.assertEqual(rows("ask") + rows("pass"), [], "nothing was done")


class LoudTest(AskedCase):
    THREE = six("one", "two", "three")

    def test_three_accepts_on_its_own_open_the_users_line_loudly(self) -> None:
        r = self.blocked_commit(self.THREE)
        self.assertEqual(self.cli(r, "known", "--accept", "legacy").returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": "broom: Claude ACCEPTED 3 findings this turn on its own: "
                                                         "broom let 3 through this turn: 3 params (accepted: legacy)"})

    def test_three_accepts_the_user_agreed_to_are_not_loud(self) -> None:
        r = self.blocked_commit(self.THREE)
        self.assertEqual(self.cli(r, "known", "--accept", "the user said yes", "--agreed").returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": "broom let 3 through this turn: 3 params (accepted, the user "
                                                         "agreed: the user said yes)"})

    def test_two_accepts_on_its_own_are_not_loud(self) -> None:
        r = self.blocked_commit(six("one", "two"))
        self.assertEqual(self.cli(r, "known", "--accept", "legacy").returncode, 0)
        self.assertEqual(self.stop(r), {"systemMessage": "broom let 2 through this turn: 2 params (accepted: legacy)"})


class BlockMessageTest(AskedCase):
    def test_a_turn_end_block_names_its_number_and_the_way_to_ask(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(SIX)
        self.edit(r)
        for n in (1, 2, 3):
            reason = self.stop(r)["reason"]
            self.assertEqual(reason.splitlines()[-1], f"Block {n} of 3. After 3 blocks the turn ends, and the user is "
                                                      "told what is still open.")
        self.assertIn('run `broom known --accept "<why>"`, then stop again. Say in your reply to the user what you '
                      "accepted and why.", reason)
        self.assertIn('If the user must decide, run `broom known --ask "<what they must decide, and why>"` and then '
                      "stop: that puts the question to them. Add --agreed to --accept only when the user said yes.",
                      reason)
        self.assertNotIn("If one predates this change", reason)

    def test_a_commit_denial_ends_with_the_same_guidance(self) -> None:
        r = self.blocked_commit()
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertEqual(reason.splitlines()[-3:], [
            "Trying again passes nothing: only a fix does, or accepting with a reason.",
            "Accept only for a real reason, such as a false positive or a refactor that comes in a later step: run "
            '`broom known --accept "<why>"`, then commit again. Say in your reply to the user what you accepted and '
            "why.",
            'If the user must decide, run `broom known --ask "<what they must decide, and why>"` and then stop: that '
            "puts the question to them. Add --agreed to --accept only when the user said yes."])

    def test_where_accepting_is_off_only_a_fix_passes_or_asking(self) -> None:
        r = self.blocked_commit()
        self.env["BROOM_NO_ACCEPT"] = "1"
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertEqual(reason.splitlines()[-2:], [
            "Trying again passes nothing. Fixing is the only way out: accepting them is off here (BROOM_NO_ACCEPT).",
            'If the user must decide, run `broom known --ask "<what they must decide, and why>"` and then stop: that '
            "puts the question to them."])
        self.assertNotIn("--accept", reason)


if __name__ == "__main__":
    import unittest

    unittest.main()
