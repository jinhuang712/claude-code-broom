"""What a turn changed, whose it is, and when its end is the end."""

from __future__ import annotations

import json
import shutil
import time
import unittest
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
        self.assertIn("huge is 120 lines long", self.stop(r, "w1", background_tasks=[])["reason"], "the real end")
        done = [{**RUNNING[0], "status": "completed"}]
        (r / "b.py").write_text(py_function("other", 120).replace("+=", "-="))
        self.edit(r, r / "b.py", "w2")
        reason = self.stop(r, "w2", background_tasks=done)["reason"]
        self.assertIn("other is 120", reason, "finished work isn't a pause")
        self.edit(r, r / "b.py", "w3")
        deferred = self.tmp / "data/sessions/w3/deferred.json"
        deferred.write_text(json.dumps({"t": time.time() - 3600}))
        self.assertIn("other is 120", self.stop(r, "w3", background_tasks=RUNNING)["reason"], "half an hour at most")

    def test_the_turn_end_sees_what_bash_changed_and_committed(self) -> None:
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 1\n"})
        self.hook("prompt", {"session_id": "t1", "cwd": str(r)})
        (r / "a.py").write_text(py_function("by_sed", 120))  # no Edit: a Bash command wrote it
        self.assertIn("by_sed is 120 lines long", self.stop(r, "t1")["reason"])
        self.assertIn("left unfixed", self.stop(r, "t1").get("systemMessage", ""), "stopping again ends the turn")
        self.hook("prompt", {"session_id": "t1", "cwd": str(r)})
        (r / "b.py").write_text(py_function("by_wrapper", 120).replace("+=", "-="))
        self.sh(r, "git", "add", "b.py")
        self.sh(r, "git", "commit", "-qm", "a wrapper committed it")  # no `git commit` from Claude to see
        reason = self.stop(r, "t1")["reason"]
        self.assertIn("by_wrapper is 120 lines long (hard limit 100; new)", reason, "measured from the prompt's HEAD")

    @unittest.skipUnless(shutil.which("oxlint"), "oxlint missing")
    def test_a_file_outside_any_repo_is_a_scratch_draft(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        draft = self.tmp / "scratchpad" / "draft.mjs"  # the kind of draft broom once stopped a turn over
        draft.parent.mkdir()
        draft.write_text("import { readdirSync } from 'node:fs';\n\nexport const x = 1;\n")
        self.edit(r, draft, "x1")
        self.assertEqual(self.stop(r, "x1"), {}, "a draft in a temp directory is no project's code")

    def test_a_subagents_edits_wait_for_its_own_end(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("worker", 120))
        self.edit(r, r / "a.py", "s1", agent="ag1")
        self.assertEqual(self.stop(r, "s1"), {}, "not the main session's to fix")
        out = self.hook("subagent-stop", {"session_id": "s1", "cwd": str(r), "agent_id": "ag1", "agent_type": "x"})
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("worker is 120 lines long", out["reason"])
