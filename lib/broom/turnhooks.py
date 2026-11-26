"""The hooks at a turn's two ends, when check_on=stop, the default.

- prompt (UserPromptSubmit): note the working tree, so the turn's end also checks what Bash changed or committed.
- stop (Stop, and SubagentStop for a subagent): lint and type-check what the turn changed. It catches what Claude
  writes even when the user commits by hand, which the commit hook never sees. A turn that ends while background
  work runs waits for a later one.

Most turns change no code. Such a turn's end reads the tree with one git call and leaves; the checks and all they
load (turncheck) are imported only for a turn that has something to check.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from . import asked, ledger
from .config import REPO_FILE, excluded, setting
from .gitutil import git_changed_files, git_root
from .state import emit, prune_sessions, read_lines
from .toolchain import lang_of
from .turns import changed_since_snapshot, note_config, paused, snapshot, tree, turn_dir, waiting


def end_turn(d: Path, root: Optional[Path], now: Optional[dict] = None) -> None:
    """Forget the turn's records; the working tree as it is now (`now`, when the caller has just read it) is where
    the next turn's changes start."""
    for name in ("edits.txt", "scan.txt", "gate.json", *ledger.TURN_NOTES):
        try:
            (d / name).unlink()
        except OSError:
            pass
    if root:
        snapshot(d, root, now)


def finish(d: Path, root: Optional[Path], tail: str = "", *, now: Optional[dict] = None, lead: str = "") -> None:
    """End the turn with one message for the user at most: `lead` if there is one (a question waiting for their answer,
    a give-up), which opens it so that it is not missed, then what the turn let through, then `tail`, what else there
    is to say. A turn that let nothing through says only the tail, with a `broom:` before it."""
    summary = ledger.through_line(d)
    end_turn(d, root, now)
    if lead:
        emit({"systemMessage": "; ".join(part for part in (lead, summary, tail) if part)})
    elif summary or tail:
        emit({"systemMessage": f"{summary}; {tail}" if summary and tail else summary or f"broom: {tail}"})


def turn_files(d: Path, since: List[Path]) -> List[Path]:
    """The code files the turn changed: recorded edits, a whole repo after a many-file Serena edit, and `since`, what
    changed or was committed since the prompt."""
    recorded = read_lines(d / "edits.txt")
    scans = read_lines(d / "scan.txt")
    files = [Path(p) for p in recorded]
    for repo in dict.fromkeys(scans):
        files += git_changed_files(Path(repo))
    return [f for f in dict.fromkeys(files + since) if lang_of(f) and f.is_file() and not excluded(f)]


def hook_stop(data: dict) -> None:
    """The turn's end, or with an agent_id a subagent's (SubagentStop), whose block goes to the subagent."""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    if setting("check_on", cwd) != "stop" or data.get("permission_mode") == "plan":
        return
    d = turn_dir(data)
    if paused(data, d):
        return  # the background work wakes a later turn, whose end checks this one's changes too
    prune_sessions()
    root = None if data.get("agent_id") else git_root(cwd)  # a subagent's end checks only the edits recorded for it
    now = tree(root) if root else None
    since = changed_since_snapshot(d, root, now) if root and now else []
    if root and root / REPO_FILE in since:
        note_config(root / REPO_FILE, d)  # loosened by a command, which no edit hook saw
    files = turn_files(d, since)
    if not files:
        finish(d, root, now=now, lead=asked.lead(asked.rows(d)))  # a question put to the user is told whatever changed
        return
    from .turncheck import Turn, check_turn  # the linters, the smells and the gate: only with code to check

    check_turn(Turn(d, root, cwd), files)


def hook_prompt(data: dict) -> None:
    """A new prompt starts a turn: note the working tree, so the turn's end sees what Bash changed or committed.
    Not while a gate is blocked or waits for background work: those changes still belong to the turn before, and the
    next turn's end that is checked checks them. It runs as an async hook (0.2 s on a 2,376-file repo, which no
    prompt should wait for); Claude's first tool call comes seconds later."""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    root = git_root(cwd)
    d = turn_dir(data)
    if waiting(d) or (d / "gate.json").exists():
        return
    ledger.forget_through(d)  # what the turn before let through or waived was never shown: no stop hook ended it
    if root and setting("check_on", cwd) == "stop":
        snapshot(d, root)
