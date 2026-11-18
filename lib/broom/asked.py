"""Asking the user: `broom known --ask "<question>"` puts a question to the user about what the last blocked commit or
turn's end showed, and passes nothing.

It is how a turn ends with a question put, where Claude may not accept a finding on its own: the findings are marked
as waiting for the user's answer for this turn only (a row each in the turn's `asked.jsonl`), the turn's end no longer
blocks on them and opens the line the user sees with `lead`, and a ledger line `ask` says it was asked. The findings stay
blocked, open in the record and unknown: a commit of that content is still denied, and the next turn's end blocks on
them again unless they were fixed, accepted or asked about again. This module loads nothing heavy: a turn's end reads
it for every turn.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from . import ledger
from .state import load_json, session_dir

SHOWN = 5  # the findings the user's line names before "and N more"


def place(entry: dict, repo: Path) -> str:
    """Where a finding is, as the user's line names it: its file relative to `repo`, and the line when there is one."""
    try:
        name = str(Path(str(entry.get("file") or "")).relative_to(repo))
    except ValueError:
        name = str(entry.get("file") or "?")
    return f"{name}:{entry['line']}" if entry.get("line") else name


def turn_of(prior: dict) -> Optional[Path]:
    """The directory of the turn a question about the last-blocked record `prior` belongs to: the turn it was blocked in.
    A block of git's own pre-commit hook belongs to no turn, so the question goes to the session `broom` runs in
    (CLAUDE_CODE_SESSION_ID), when it is told which."""
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if prior.get("where") == "pre-commit" and session:
        return session_dir(session)
    return Path(prior["turn"]) if prior.get("turn") else None


def ask_blocked(repo: Path, question: str) -> int:
    """Mark the issues of the last commit or turn end broom blocked in `repo` as waiting for the user's answer in the
    turn they were blocked in, and write an `ask` line for each. Nothing becomes known and nothing passes: the record
    keeps them pending, so `--accept` still serves them after the user answers. Returns how many; 0 with nothing
    blocked."""
    from .gate import COMMITS  # the command is the only one that needs it

    prior = load_json(COMMITS, {}).get(str(repo)) or {}
    pending = prior.get("pending") or {}
    ledger.write([ledger.finding("ask", k, e, why=question, where=prior.get("where") or "commit")
                  for k, e in pending.items()])
    turn = turn_of(prior)
    if turn is not None:
        ledger.note_turn(turn, ledger.ASKED, [{"key": k, "why": question, "repo": str(repo), "at": place(e, repo),
                                               "entry": e} for k, e in pending.items()])
    return len(pending)


def rows(turn: Path) -> List[dict]:
    """The findings the turn asked the user about, one row each (its `key`, the `why` of the question, its `repo`, where
    it is `at` and its `entry`), the last question about a finding the one that stands."""
    return list({r["key"]: r for r in ledger.read(turn / ledger.ASKED) if r.get("key")}.values())


def entries(waiting: List[dict]) -> Dict[str, dict]:
    """The findings of the `waiting` rows by key, as the entries the record and the ledger take."""
    return {r["key"]: r.get("entry") or {} for r in waiting}


def lead(waiting: List[dict]) -> str:
    """The part of the user's line that opens it when findings wait for the user: `broom: 1 finding WAITS FOR YOUR
    ANSWER: api/stock.py:56 params: <the question>`. Findings asked in one question are named together; the first SHOWN
    of each, and how many more. Empty when none wait."""
    by_question: Dict[str, List[dict]] = {}
    for r in waiting:
        by_question.setdefault(str(r.get("why")), []).append(r)
    parts = []
    for question, group in by_question.items():
        named = [f"{r.get('at')} {(r.get('entry') or {}).get('rule')}" for r in group][:SHOWN]
        more = f", and {len(group) - SHOWN} more" if len(group) > SHOWN else ""
        parts.append(f"{', '.join(named)}{more}: {question}")
    if not parts:
        return ""
    n = len(waiting)
    return f"broom: {n} finding{'' if n == 1 else 's'} WAIT{'S' if n == 1 else ''} FOR YOUR ANSWER: " + " | ".join(parts)
