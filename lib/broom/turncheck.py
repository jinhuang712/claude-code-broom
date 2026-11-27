"""The check at a turn's end, for a turn that changed code (turnhooks decides that, and loads this module only then).

A turn's end blocks like a commit, and stopping again passes nothing: what is left, a hint with the rest, is fixed, or
accepted with `broom known --accept "<why>"`, or put to the user with `broom known --ask "<question>"`, which blocks
no more in this turn and opens the user's line with `broom: ... WAITS FOR YOUR ANSWER`. After MAX_BLOCKS blocks broom
gives up, as it never traps a turn: the turn ends, what is left is on record as `gave-up`, and the user is told in a
line that opens `broom GAVE UP`. A nit, a slight smell, never blocks: the user's line at the turn's end tells it, once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional

from . import asked, ledger
from .comeback import settle_covered
from .commitgate import checked, collapsed_line, collapsed_text, entries_of, issues_by_repo, way_out
from .findings import Issue
from .gate import (
    STOPS, baseline_keys, issue_key, kept_blocks, last_block, load_commits, new_notes, note_text, rel, render,
    save_commits, setup_hint,
)
from .smells import Smell
from .state import append_line, emit, load_json, read_lines, save_json
from .testrun import accepted_here, findings as test_findings
from .turnhooks import finish
from .turns import turn_base

BLOCKED_IN = "blocked-in.txt"  # in a turn's directory: the repos its turn-end blocks were noted in, one per line
MAX_BLOCKS = 3  # how often a turn's end blocks before it gives up
SHOWN = 5  # the findings a line for the user names before "and N more"


def turn_head(count: int) -> str:
    """The first line of a turn-end block: what was found, and the first thing to do about it."""
    return f"[broom] {count} issue(s) in this turn's changes. Fix them before finishing."


def turn_way_out(repos: List[Path], cwd: Path, blocks: int) -> str:
    """The last of a turn-end block's own lines: stopping again passes nothing, so fix what is left, accept it with a
    reason or ask the user; which block this is of MAX_BLOCKS; and that after them the turn ends with the user told
    what is still open."""
    leave = (f"Block {blocks} of {MAX_BLOCKS}. After {MAX_BLOCKS} blocks the turn ends, and the user is told what is "
             "still open.")
    return f"{way_out(repos or [cwd], cwd, 'stop again')}\n{leave}"


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


def blocked_in(d: Path) -> List[Path]:
    """The repos the turn-end blocks of the turn in `d` were noted in."""
    return [Path(p) for p in dict.fromkeys(read_lines(d / BLOCKED_IN))]


def turn_records(state: dict, d: Path) -> List[str]:
    """The repos whose last-blocked record in `state` (commits.json) is a turn-end block of the turn in `d`."""
    return [k for k, v in state.items() if isinstance(v, dict) and v.get("turn") == str(d) and v.get("where") in STOPS]


def note_turn_block(d: Path, groups: Dict[Path, List[Issue]], waiting: List[dict]) -> None:
    """Keep what a turn-end block showed in each repo's last-blocked record (commits.json), where `broom known
    --accept` finds it, as it does what a commit blocked. A turn-end block takes the place of the last block, and what
    a commit blocked before stays in it as `earlier`: no turn-end check covers their files, and the commit that fixes
    them still has their fix lines to write. What this block shows again is its own to end. An earlier turn-end block
    is no part of it: its turn's gate.json holds it. What the turn asked the user about (`waiting`) stays in it,
    for `broom known --accept` to serve once the user has answered."""
    state, known = load_commits(groups), baseline_keys(groups)
    for repo in groups:
        if str(repo) not in read_lines(d / BLOCKED_IN):
            append_line(d / BLOCKED_IN, str(repo))
    for repo, issues in groups.items():
        shown = {**entries_of(issues), **asked.entries([r for r in waiting if r.get("repo") == str(repo)])}
        state[str(repo)] = last_block(shown, kept_blocks(state.get(str(repo)), known, shown), d)
    save_commits(state, groups)


def held(d: Path) -> Dict[str, dict]:
    """What the turn-end blocks of the session in `d` left in the repos' last-blocked records: the findings an earlier
    turn asked the user about, which this turn's end must see fixed to write their fix lines."""
    state = load_commits(blocked_in(d))
    return {k: e for repo in turn_records(state, d) for k, e in (state[repo].get("pending") or {}).items()}


def forget_turn_blocks(d: Path, waiting: Iterable[str] = ()) -> None:
    """The turn's end is done with what its blocks left in commits.json (nothing to block, or it gave up): drop it, so
    a later `broom known --accept` doesn't accept what is gone or pass it a second time. What a commit blocked before
    them stays, to be fixed; so do the findings of the turn that wait for the user (their keys in `waiting`), which the
    user's answer may accept."""
    state = load_commits(blocked_in(d))
    mine, wait = turn_records(state, d), set(waiting)
    for k in mine:
        left = {key: e for key, e in (state[k].get("pending") or {}).items() if key in wait}
        if state[k].get("earlier") or left:
            state[k] = {**state[k], "pending": left}
        else:
            state.pop(k)
    if mine:
        save_commits(state, mine)


def block_turn(d: Path, blocking: List[Issue], progress: dict, reason: str, waiting: List[dict]) -> None:
    """Block the turn's end with `reason`, and note what Claude was shown: in gate.json, with the count of blocks in
    `progress`, and in commits.json, for `broom known --accept`, with what waits for the user."""
    found = entries_of(blocking)
    ledger.blocked(found)
    save_json(d / "gate.json", {**progress, "blocked": found})
    note_turn_block(d, issues_by_repo(blocking), waiting)
    emit({"decision": "block", "reason": reason})


class Turn(NamedTuple):
    """A turn at its end, as turnhooks found it."""

    d: Path  # where its records are
    root: Optional[Path]  # the session's repo; None for a subagent
    cwd: Path  # where the hook runs


def end_tail(d: Path, notes: List[str], files: List[Path], told: List[Smell], collapsed: int = 0) -> str:
    """What a turn's end adds to the user's line besides what was let through: the checks that didn't run, which are
    told once a session, the nits (slight smells), which the turn's end tells once since it ends the turn, and how
    many known issues the check `collapsed`, which the caller passes only when the check has something else to say."""
    skipped = new_notes(d / "notes.json", notes, files[0])
    parts = []
    if skipped:
        parts.append("; ".join(note_text(n) for n in skipped) + (" (run /broom:setup)" if setup_hint(skipped) else ""))
    if told:
        parts.append(f"{len(told)} nit(s) told: {names([s.issue() for s in told])}")
    return "; ".join(parts + ([collapsed_text(collapsed)] if collapsed else []))


def give_up(turn: Turn, blocking: List[Issue], tail: str, waiting: List[dict]) -> None:
    """The turn has been blocked MAX_BLOCKS times and still has findings: end it. What is left is on record as
    `gave-up`, not known; the repo's last-blocked record lets go of it, so a later `broom known --accept` can't pass it
    a second time; and the user's line opens with `gave_up_line`, ahead of the rest of the turn's summary, after the
    question of what waits for their answer."""
    ledger.let_through(entries_of(blocking), "gave-up", turn.d)
    forget_turn_blocks(turn.d, [r["key"] for r in waiting])
    finish(turn.d, turn.root, tail, lead="; ".join(x for x in (asked.lead(waiting), gave_up_line(blocking)) if x))


def settle_asks(d: Path, gate: dict, blocking: List[Issue], files: List[Path], notes: List[str]) -> List[dict]:
    """Write the fix lines of what this check finds gone of what the turn's blocks showed (`gate`) and of what the turn
    asked the user about, which the record of the session's turn-end blocks holds too; and give the rows of what still
    waits for the user's answer: asked about in this turn, and neither fixed nor accepted since."""
    waiting = asked.rows(d)
    prior = {**held(d), **asked.entries(waiting), **(gate.get("blocked") or {})}
    known = baseline_keys(files) | accepted_here(d)  # what was accepted for this turn only is as good as known in it
    gone = ledger.fixes(prior, entries_of(blocking), known, files, notes) if prior else set()
    settle_covered(files, {issue_key(i) for i in blocking}, prior)  # what other turns and sessions left open in them
    return [r for r in waiting if r["key"] not in gone and r["key"] not in known]


def check_turn(turn: Turn, files: List[Path]) -> None:
    """Check the code `files` the turn changed: block its end while a finding is left, up to MAX_BLOCKS times, then
    give up; or end it. Stopping again re-checks, with or without an edit: nothing but a fix, an accepted reason or a
    question put to the user passes, and the question only for this turn."""
    d = turn.d
    gate = load_json(d / "gate.json", {})
    blocking, told, notes, collapsed = checked(files, turn_base(d, turn.root), d)
    blocking += test_findings(d, turn.root, files)  # a main session's turn only
    waiting = settle_asks(d, gate, blocking, files, notes)
    asked_keys = {r["key"] for r in waiting}
    blocking = [i for i in blocking if issue_key(i) not in asked_keys]
    if not blocking:
        forget_turn_blocks(d, asked_keys)
        finish(d, turn.root, end_tail(d, notes, files, told, collapsed if told else 0), lead=asked.lead(waiting))
        return
    blocks = int(gate.get("blocks", 0)) + 1
    if blocks > MAX_BLOCKS:
        give_up(turn, blocking, end_tail(d, notes, files, told, collapsed), waiting)
        return
    groups = issues_by_repo(blocking)
    reason = render(turn_head(len(blocking)), blocking, new_notes(d / "notes.json", notes, files[0]), set(files),
                    turn_way_out(list(groups), turn.cwd, blocks))
    reason = "\n".join([reason] + collapsed_line(collapsed))
    block_turn(d, blocking, {"blocks": blocks}, reason, waiting)
