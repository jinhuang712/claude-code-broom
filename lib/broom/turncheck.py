"""The check at a turn's end, for a turn that changed code (turnhooks decides that, and loads this module only then).

A turn's end blocks like a commit, once: accept what is left with `broom known --accept "<why>"` and stop again.
Stopping again without that still ends the turn, as broom never traps one, but records nothing as known: what is
left stays open and shows in the turn's summary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from . import ledger
from .commitgate import checked, entries_of, issues_by_repo, way_out
from .findings import Issue
from .gate import COMMITS, baseline_keys, new_notes, note_text, render, save_commits, setup_hint, verdict
from .state import emit, load_json, save_json
from .turnhooks import finish
from .turns import turn_base

MAX_BLOCKS = 3  # how often a turn's end blocks before it gives up
STOPS = ("stop", "subagent-stop")  # the hooks of a turn's end, as the ledger and commits.json name them


def stop_again(d: Path, root: Optional[Path], gate: dict) -> None:
    """Claude stopped again without editing: the turn ends. Nothing becomes known: what is left, less what was
    accepted since, stays open, and is noted as let through with how `turn-ended`."""
    known = baseline_keys()
    left = {k: e for k, e in (gate.get("blocked") or {}).items() if k not in known}
    ledger.let_through(left, "turn-ended", d)
    finish(d, root, f"{len(left)} issue(s) left unfixed" if left else "")


def turn_head(count: int) -> str:
    """The first line of a turn-end block: what was found, and the first thing to do about it."""
    return f"[broom] {count} issue(s) in this turn's changes. Fix them before finishing."


def turn_way_out(repos: List[Path], cwd: Path) -> str:
    """The last of a turn-end block's own lines: accept what is left with a reason and stop again, or stop again and
    leave it open."""
    leave = "Stopping again ends the turn, but leaves the issues open: a commit still stops on them."
    return f"{way_out(repos or [cwd], cwd, 'stop again')} {leave}"


def commit_blocked(record: object, shown: Dict[str, dict]) -> Dict[str, dict]:
    """What a commit blocked in a repo and no check has ended, from the repo's last-blocked `record` (commits.json):
    a turn-end block takes the place of the last block, and these findings stay behind it as `earlier`, since no
    turn-end check covers their files and the commit that fixes them still has their fix lines to write. What this
    block `shown` again is its own to end. An earlier turn-end block is no part of it: its turn's gate.json holds it."""
    if not isinstance(record, dict):
        return {}
    last = {} if record.get("where") in STOPS else record.get("pending") or {}
    return {k: e for k, e in {**(record.get("earlier") or {}), **last}.items() if k not in shown}


def note_turn_block(d: Path, groups: Dict[Path, List[Issue]]) -> None:
    """Keep what a turn-end block showed in each repo's last-blocked record (commits.json), where `broom known
    --accept` finds it, as it does what a commit blocked; what a commit blocked before stays in it as `earlier`."""
    state = load_json(COMMITS, {})
    for repo, issues in groups.items():
        shown = entries_of(issues)
        state[str(repo)] = {"pending": shown, "where": ledger.HOOK.where, "turn": str(d),
                            "earlier": commit_blocked(state.get(str(repo)), shown)}
    save_commits(state, groups)


def forget_turn_blocks(d: Path) -> None:
    """The turn's end found nothing to block: drop what its blocks left in commits.json, so a later `broom known
    --accept` doesn't accept what is gone. What a commit blocked before them stays, to be fixed."""
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
    """Block the turn's end with `reason`, and note what Claude was shown: in gate.json, so that stopping again ends
    the turn, and in commits.json, for `broom known --accept`."""
    found = entries_of(blocking)
    ledger.blocked(found)
    save_json(d / "gate.json", {"verdict": verdict(blocking), "count": len(blocking), **progress, "blocked": found})
    note_turn_block(d, issues_by_repo(blocking))
    emit({"decision": "block", "reason": reason})


class Turn(NamedTuple):
    """A turn at its end, as turnhooks found it."""

    d: Path  # where its records are
    root: Optional[Path]  # the session's repo; None for a subagent
    cwd: Path  # where the hook runs
    mark: str  # changes whenever one of the turn's files does: the same as at the last block means no new edit


def check_turn(turn: Turn, files: List[Path]) -> None:
    """Check the code `files` the turn changed: block its end once, or end it."""
    d, root = turn.d, turn.root
    gate = load_json(d / "gate.json", {})
    if gate.get("verdict") and gate.get("edits_at") == turn.mark:
        stop_again(d, root, gate)
        return
    blocking, hints, notes = checked(files, turn_base(d, root), d)
    blocking += [s.issue() for s in hints]  # at a turn's end a hint stops Claude once: it cleans up now
    if gate.get("blocked"):
        ledger.fixes(gate["blocked"], entries_of(blocking), baseline_keys(), files, notes)
    if not blocking:
        forget_turn_blocks(d)
        fresh = new_notes(d / "notes.json", notes, files[0])
        tail = "; ".join(note_text(n) for n in fresh) + (" (run /broom:setup)" if setup_hint(fresh) else "")
        finish(d, root, tail if fresh else "")
        return
    blocks = int(gate.get("blocks", 0)) + 1
    if blocks > MAX_BLOCKS:
        ledger.let_through(entries_of(blocking), "gave-up", d)
        finish(d, root, f"gave up after {MAX_BLOCKS} rounds, {len(blocking)} issue(s) left")
        return
    groups = issues_by_repo(blocking)
    reason = render(turn_head(len(blocking)), blocking, new_notes(d / "notes.json", notes, files[0]), set(files),
                    turn_way_out(list(groups), turn.cwd))
    block_turn(d, blocking, {"edits_at": turn.mark, "blocks": blocks}, reason)
