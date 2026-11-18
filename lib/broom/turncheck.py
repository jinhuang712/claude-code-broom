"""The check at a turn's end, for a turn that changed code (turnhooks decides that, and loads this module only then).

A turn's end blocks like a commit, and stopping again passes nothing: what is left, a hint with the rest, is fixed, or
accepted with `broom known --accept "<why>"`. After MAX_BLOCKS blocks broom gives up, as it never traps a turn: the
turn ends, what is left is on record as `gave-up`, and the user is told in a line that opens `broom GAVE UP`. A note,
a slight smell, never blocks: the user's line at the turn's end tells it, once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from . import ledger
from .commitgate import checked, entries_of, issues_by_repo, way_out
from .findings import Issue
from .gate import (
    COMMITS, STOPS, baseline_keys, kept_blocks, last_block, new_notes, note_text, rel, render, save_commits,
    setup_hint,
)
from .smells import Smell
from .state import emit, load_json, save_json
from .turnhooks import finish
from .turns import turn_base

MAX_BLOCKS = 3  # how often a turn's end blocks before it gives up
SHOWN = 5  # the findings a line for the user names before "and N more"


def turn_head(count: int) -> str:
    """The first line of a turn-end block: what was found, and the first thing to do about it."""
    return f"[broom] {count} issue(s) in this turn's changes. Fix them before finishing."


def turn_way_out(repos: List[Path], cwd: Path) -> str:
    """The last of a turn-end block's own lines: stopping again passes nothing, so fix what is left or accept it with a
    reason; and after MAX_BLOCKS blocks the turn ends with the user told what is still open."""
    leave = f"After {MAX_BLOCKS} blocks the turn ends, and the user is told what is still open."
    return f"{way_out(repos or [cwd], cwd, 'stop again')} {leave}"


def names(issues: List[Issue]) -> str:
    """The first SHOWN of `issues` as `a.py:12 function_lines, b.py:3 skipped_test`, with how many more."""
    ordered = sorted(issues, key=lambda i: (str(i.file), i.line))
    where = [f"{rel(i.file, i.root)}:{i.line}" if i.line else rel(i.file, i.root) for i in ordered]
    shown = [f"{w} {i.rule}" for w, i in zip(where, ordered)][:SHOWN]
    return ", ".join(shown) + (f", and {len(ordered) - SHOWN} more" if len(ordered) > SHOWN else "")


def gave_up_line(blocking: List[Issue]) -> str:
    """The line the user sees when broom gives up: it opens so that it can't be missed, and names what is left."""
    return (f"broom GAVE UP after {MAX_BLOCKS} blocks: {len(blocking)} finding(s) left unfixed and unaccepted: "
            f"{names(blocking)}")


def note_turn_block(d: Path, groups: Dict[Path, List[Issue]]) -> None:
    """Keep what a turn-end block showed in each repo's last-blocked record (commits.json), where `broom known
    --accept` finds it, as it does what a commit blocked. A turn-end block takes the place of the last block, and what
    a commit blocked before stays in it as `earlier`: no turn-end check covers their files, and the commit that fixes
    them still has their fix lines to write. What this block shows again is its own to end. An earlier turn-end block
    is no part of it: its turn's gate.json holds it."""
    state, known = load_json(COMMITS, {}), baseline_keys()
    for repo, issues in groups.items():
        shown = entries_of(issues)
        state[str(repo)] = last_block(shown, kept_blocks(state.get(str(repo)), known, shown), d)
    save_commits(state, groups)


def forget_turn_blocks(d: Path) -> None:
    """The turn's end is done with what its blocks left in commits.json (nothing to block, or it gave up): drop it, so
    a later `broom known --accept` doesn't accept what is gone or pass it a second time. What a commit blocked before
    them stays, to be fixed."""
    state = load_json(COMMITS, {})
    mine = [k for k, v in state.items() if isinstance(v, dict) and v.get("turn") == str(d) and v.get("where") in STOPS]
    for k in mine:
        if state[k].get("earlier"):
            state[k] = {**state[k], "pending": {}}
        else:
            state.pop(k)
    if mine:
        save_commits(state, mine)


def block_turn(d: Path, blocking: List[Issue], progress: dict, reason: str) -> None:
    """Block the turn's end with `reason`, and note what Claude was shown: in gate.json, with the count of blocks in
    `progress`, and in commits.json, for `broom known --accept`."""
    found = entries_of(blocking)
    ledger.blocked(found)
    save_json(d / "gate.json", {**progress, "blocked": found})
    note_turn_block(d, issues_by_repo(blocking))
    emit({"decision": "block", "reason": reason})


class Turn(NamedTuple):
    """A turn at its end, as turnhooks found it."""

    d: Path  # where its records are
    root: Optional[Path]  # the session's repo; None for a subagent
    cwd: Path  # where the hook runs


def end_tail(d: Path, notes: List[str], files: List[Path], told: List[Smell]) -> str:
    """What a turn's end adds to the user's line besides what was let through: the checks that didn't run, which are
    told once a session, and the notes (slight smells), which the turn's end tells once since it ends the turn."""
    skipped = new_notes(d / "notes.json", notes, files[0])
    parts = []
    if skipped:
        parts.append("; ".join(note_text(n) for n in skipped) + (" (run /broom:setup)" if setup_hint(skipped) else ""))
    if told:
        parts.append(f"{len(told)} slight smell(s) noted: {names([s.issue() for s in told])}")
    return "; ".join(parts)


def give_up(turn: Turn, blocking: List[Issue], tail: str) -> None:
    """The turn has been blocked MAX_BLOCKS times and still has findings: end it. What is left is on record as
    `gave-up`, not known; the repo's last-blocked record lets go of it, so a later `broom known --accept` can't pass it
    a second time; and the user's line opens with `gave_up_line`, ahead of the rest of the turn's summary."""
    ledger.let_through(entries_of(blocking), "gave-up", turn.d)
    forget_turn_blocks(turn.d)
    finish(turn.d, turn.root, tail, lead=gave_up_line(blocking))


def check_turn(turn: Turn, files: List[Path]) -> None:
    """Check the code `files` the turn changed: block its end while a finding is left, up to MAX_BLOCKS times, then
    give up; or end it. Stopping again re-checks, with or without an edit: nothing but a fix, or an accepted
    reason, passes."""
    d = turn.d
    gate = load_json(d / "gate.json", {})
    blocking, told, notes = checked(files, turn_base(d, turn.root), d)
    if gate.get("blocked"):
        ledger.fixes(gate["blocked"], entries_of(blocking), baseline_keys(), files, notes)
    if not blocking:
        forget_turn_blocks(d)
        finish(d, turn.root, end_tail(d, notes, files, told))
        return
    blocks = int(gate.get("blocks", 0)) + 1
    if blocks > MAX_BLOCKS:
        give_up(turn, blocking, end_tail(d, notes, files, told))
        return
    groups = issues_by_repo(blocking)
    reason = render(turn_head(len(blocking)), blocking, new_notes(d / "notes.json", notes, files[0]), set(files),
                    turn_way_out(list(groups), turn.cwd))
    block_turn(d, blocking, {"blocks": blocks}, reason)
