"""Throwaway repos with a history for the diagnosis tests: commits made on a given day, and files written the way a
test lists them."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from support import BroomCase


def days_ago(days: int) -> str:
    """A commit date `days` days back, in the form git reads."""
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


class GitWork(BroomCase):
    """A BroomCase that can commit on a day of its choice. It holds no tests itself."""

    def history_repo(self, steps: list) -> Path:
        """A new repo with one commit per step, oldest first: each step is (days ago, {file: text})."""
        d = self.tmp / f"history{len(list(self.tmp.glob('history*')))}"
        d.mkdir()
        self.sh(d, "git", "init", "-q")
        for days, files in steps:
            self.commit_all(d, files, days_ago(days))
        return d

    def commit_all(self, r: Path, files: dict, date: str = "") -> None:
        """Write `files` and commit them, at `date` when it is given."""
        for name, body in files.items():
            (r / name).parent.mkdir(parents=True, exist_ok=True)
            (r / name).write_text(body)
        self.sh(r, "git", "add", "-A")
        dates = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}
        done = subprocess.run(["git", "commit", "-qm", "c"], cwd=r, env={**self.env, **dates}, capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr)
