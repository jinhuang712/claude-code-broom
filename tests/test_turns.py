"""What a turn changed, whose it is, and when its end is the end."""

from __future__ import annotations

import subprocess
from pathlib import Path

from support import BroomCase, py_function

RUNNING = [{"id": "b1", "type": "local_bash", "status": "running", "description": "the test suite"}]


class TurnTest(BroomCase):
    def edit(self, r: Path, path: Path, session: str, agent: str = "") -> None:
        self.hook("edit", {"session_id": session, "cwd": str(r), "tool_name": "Edit",
                           "tool_input": {"file_path": str(path)}, **({"agent_id": agent} if agent else {})})

    def stop(self, r: Path, session: str, **extra: object) -> dict:
        return self.hook("stop", {"session_id": session, "cwd": str(r), "permission_mode": "default", **extra})

    def test_a_turn_ending_while_background_work_runs_waits(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.edit(r, r / "a.py", "w1")
        self.assertEqual(self.stop(r, "w1", background_tasks=RUNNING), {}, "a pause: the gate waits")
        self.assertIn("huge is 120 code lines long", self.stop(r, "w1", background_tasks=[])["reason"], "the real end")
        done = [{**RUNNING[0], "status": "completed"}]
        (r / "b.py").write_text(py_function("other", 120).replace("+=", "-="))
        self.edit(r, r / "b.py", "w2")
        reason = self.stop(r, "w2", background_tasks=done)["reason"]
        self.assertIn("other is 120", reason, "finished work isn't a pause")

    def test_work_waited_for_once_is_not_waited_for_again(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.hook("prompt", {"session_id": "w4", "cwd": str(r)})
        self.assertEqual(self.stop(r, "w4", background_tasks=RUNNING), {}, "the first sight of the work: a pause")
        self.hook("prompt", {"session_id": "w4", "cwd": str(r)})
        (r / "a.py").write_text(py_function("huge", 120))
        self.edit(r, r / "a.py", "w4")
        reason = self.stop(r, "w4", background_tasks=RUNNING)["reason"]
        self.assertIn("huge is 120", reason, "the same work still running at the next turn's end: checked")
        other = [*RUNNING, {"id": "b2", "type": "local_bash", "status": "running", "description": "a build"}]
        self.assertEqual(self.stop(r, "w4", background_tasks=other), {}, "new work beside it: a pause again")

    def test_the_turn_end_sees_what_bash_changed_and_committed(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.hook("prompt", {"session_id": "t1", "cwd": str(r)})
        (r / "a.py").write_text(py_function("by_sed", 120))  # no Edit: a Bash command wrote it
        self.assertIn("by_sed is 120 code lines long", self.stop(r, "t1")["reason"])
        self.assertIn("by_sed is 120 code lines long", self.stop(r, "t1")["reason"], "stopping again passes nothing")
        self.hook("prompt", {"session_id": "t1", "cwd": str(r)})
        (r / "b.py").write_text(py_function("by_wrapper", 120).replace("+=", "-="))
        self.sh(r, "git", "add", "b.py")
        self.sh(r, "git", "commit", "-qm", "a wrapper committed it")  # no `git commit` from Claude to see
        reason = self.stop(r, "t1")["reason"]
        self.assertIn("by_wrapper is 120 code lines long (hard limit 100; new)", reason, "measured from the prompt's HEAD")

    def test_commits_the_turn_brought_in_are_not_its_own(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        branch = self.sh(r, "git", "branch", "--show-current").strip()
        self.sh(r, "git", "checkout", "-qb", "upstream")
        (r / "b.py").write_text(py_function("theirs", 120))
        (r / "c.py").write_text(py_function("elsewhere", 120).replace("+=", "-="))
        self.sh(r, "git", "add", "b.py", "c.py")
        subprocess.run(["git", "commit", "-qm", "pushed before the prompt"], cwd=r, check=True,
                       env={**self.env, "GIT_COMMITTER_DATE": "2026-01-01T00:00:00"})
        self.sh(r, "git", "checkout", "-q", branch)
        self.hook("prompt", {"session_id": "p1", "cwd": str(r)})
        self.sh(r, "git", "merge", "-q", "--ff-only", "upstream")  # a pull
        with (r / "b.py").open("a") as f:
            f.write('\n\ndef mine() -> int:\n    """Mine."""\n    return 1\n')
        self.edit(r, r / "b.py", "p1")
        reason = self.stop(r, "p1").get("reason", "")
        self.assertNotIn("theirs is 120", reason, "measured from what the pull brought, not from the prompt's HEAD")
        self.assertNotIn("elsewhere", reason, "a file only the pull changed is not the turn's")

    def test_the_next_prompt_ends_a_wait(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        self.hook("prompt", {"session_id": "g1", "cwd": str(r)})
        (r / "a.py").write_text(py_function("mine", 120))
        self.edit(r, r / "a.py", "g1")
        self.assertEqual(self.stop(r, "g1", background_tasks=RUNNING), {}, "a pause")
        (r / "b.py").write_text(py_function("theirs", 120).replace("+=", "-="))
        self.sh(r, "git", "add", "b.py")
        self.sh(r, "git", "commit", "-qm", "another session landed its work")
        self.hook("prompt", {"session_id": "g1", "cwd": str(r)})  # the work never woke a turn
        reason = self.stop(r, "g1").get("reason", "")
        self.assertNotIn("theirs", reason, "the new prompt noted the tree")
        self.assertIn("mine is 120", reason, "the waiting turn's edits are checked at the new turn's end")

    def test_a_subagents_edits_wait_for_its_own_end(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("worker", 120))
        self.edit(r, r / "a.py", "s1", agent="ag1")
        self.assertEqual(self.stop(r, "s1"), {}, "not the main session's to fix")
        out = self.hook("subagent-stop", {"session_id": "s1", "cwd": str(r), "agent_id": "ag1", "agent_type": "x"})
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("worker is 120 code lines long", out["reason"])
