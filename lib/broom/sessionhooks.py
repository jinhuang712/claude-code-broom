"""The hooks at a session's start (SessionStart).

- session: tell Claude the limits card (see card), and when the repo is missing tools or configs broom needs, ask
  Claude to offer the user /broom:setup. Hooks can't ask the user anything themselves; Claude does, with the user's
  consent. The smell note comes from a scan of HEAD, cached.
- session-scan, an async hook: run that scan when there is none, then the check-up.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .card import limits_card
from .checkup import check_up_time
from .config import setting
from .doctor import describe, diagnose_cached, new_gaps
from .gitutil import git_root
from .hotspots import cached_summary, session_note, summary
from .state import append_line, emit, read_lines, session_dir


def hook_session(data: dict) -> None:
    """Notes for Claude's first turn, which waits for this hook: so only what is quick, the cached doctor and the
    smell counts of a scan that already ran. The limits card comes first, then the offer of setup, then the smells."""
    repo = git_root(Path(data.get("cwd") or os.getcwd()).resolve())
    if repo is None:
        return
    sd = session_dir(data.get("session_id") or "cli")
    if str(repo) in read_lines(sd / "nudged.txt"):
        return  # once per session: a compaction or /clear doesn't repeat it
    diagnosis = diagnose_cached(repo)
    smells = session_note(repo, cached_summary(repo))
    notes = [n for n in (limits_card(repo, diagnosis), setup_note(repo, diagnosis), smells) if n]
    if smells:
        append_line(sd / "smells-noted.txt", str(repo))
    if not notes:
        return
    append_line(sd / "nudged.txt", str(repo))
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(notes)}})


def scan_note(repo: Path, sd: Path, data: Optional[dict]) -> Optional[str]:
    """The smell note from a scan's summary, unless this session was told it already."""
    note = session_note(repo, data)
    if note and str(repo) not in read_lines(sd / "smells-noted.txt"):
        append_line(sd / "smells-noted.txt", str(repo))
        return note
    return None


def hook_session_scan(data: dict) -> None:
    """The scan behind the smell note, in the background (an async hook) when HEAD has none cached; then the check-up
    (see checkup), which counts what the scan counted and the files' rot. What either has to say reaches Claude with
    its next turn."""
    repo = git_root(Path(data.get("cwd") or os.getcwd()).resolve())
    if repo is None or setting("smells", repo) == "off":
        return
    cached = cached_summary(repo)
    whole = cached is not None and not cached.get("partial")
    found = cached if whole else summary(repo)
    # With a whole cached scan, the session hook has already said what there is to say about the smells.
    notes = [None if whole else scan_note(repo, session_dir(data.get("session_id") or "cli"), found),
             check_up_time(repo, found)]
    told = [n for n in notes if n]
    if told:
        emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(told)}})


SETUP_NOTE_GAPS = 6  # how many gaps the session note names before "and N more"


def setup_note(repo: Path, diagnosis: dict) -> Optional[str]:
    """The note offering /broom:setup for the gaps in `diagnosis` that the user hasn't answered, or None."""
    found = new_gaps(repo, diagnosis)  # gaps the user already answered, in any repo, stay quiet
    if not found:
        return None
    more = f"; and {len(found) - SETUP_NOTE_GAPS} more" if len(found) > SETUP_NOTE_GAPS else ""
    summary = "; ".join(describe(i) for i in found[:SETUP_NOTE_GAPS]) + more
    return (f"broom (the code-hygiene plugin) found gaps in this repo: {summary}. At a natural point, and before "
            "your first commit here at the latest, offer the user /broom:setup. Don't install anything they haven't "
            "agreed to; if they decline, run `broom setup --dismiss` so broom stops asking, here and in other repos, "
            "until a new kind of gap turns up.")
