"""Open findings come back (F2.14, decision 044): a finding that stopped a commit or a turn's end and that no check has
ended (no fix line, no pass line: what `broom report` counts as open) is told to Claude again, until it is fixed or
accepted. It tells and never blocks.

It is told at 2 moments:

- The next prompt after a question put with `broom known --ask`, which holds the user's answer. The question left the
  findings asked about in the session's `answer-due.jsonl` (asked.DUE). Claude must be told in the turn that answers,
  and an async hook's output reaches Claude only on a later turn, so a synchronous hook tells them at once from the
  record (`hook_answer`; hooks/prompt.sh leaves before Python starts while no question waits). The prompt's async hook
  then checks their files again (`recheck_answered`), records what is gone as fixed, and says so on the next turn.
- A session's start in the repo, in the async session scan (`session_note`): every finding still open there, asked
  about or not.

Before the session's start tells, the files of those findings are checked again with the rules of the day: a finding
no longer there gets a `fix` line and is not told. One whose file is gone, or which no check covers any more (an
excluded file, smells turned off), leaves with no line and is not told. A check that didn't run (a timeout, a missing
tool) ends nothing: its findings are told. The `tests` finding of a turn (F2.13) belongs to its turn and is left out.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from . import asked, ledger
from .config import NIT, TESTS_TOOL, excluded, setting
from .gitutil import CLOCK, main_worktree
from .state import emit
from .toolchain import lang_of

SHOWN = 5  # the findings a message names before "and N more"
MIN_SECONDS = 6  # a hook with less time left than this tells the findings without checking their files again
SMELL_SECONDS = 15  # what the tools that run in the real tree have between them in a check again, at most
Group = Tuple[str, object, object]  # (the file's resolved path, the tool, the rule)


# ---------------------------------------------------------------- the record


def standing(repo: str) -> Dict[str, dict]:
    """The findings of `repo` (a main worktree, as the ledger names it) that no check has ended, by key: the last block
    line of each, with `asked` when the user was asked about it. A `tests` finding is left out: it is its turn's."""
    last: Dict[str, dict] = {}
    asked_keys: Set[str] = set()
    for r in ledger.read(ledger.LEDGER, json.dumps(repo)[1:-1]):
        if r.get("repo") != repo or not r.get("key"):
            continue
        if r.get("event") == "ask":
            asked_keys.add(r["key"])
        elif r.get("event") in ledger.OUTCOME_EVENTS:
            last[r["key"]] = r
    return {k: {**r, "asked": k in asked_keys} for k, r in last.items()
            if r["event"] == "block" and r.get("tool") != TESTS_TOOL}


def place(row: dict) -> str:
    """Where a finding of the record is and its rule: `a.py:12 params`, or `a.py params` for a line with no number."""
    where = f"{row.get('file')}:{row['line']}" if row.get("line") else str(row.get("file"))
    return f"{where} {row.get('rule')}"


def named(labels: List[str]) -> str:
    """The first SHOWN of `labels`, and how many more."""
    return ", ".join(labels[:SHOWN]) + (f", and {len(labels) - SHOWN} more" if len(labels) > SHOWN else "")


# ---------------------------------------------------------------- checking again


def covered(file: Path) -> bool:
    """Whether a check still covers `file`: it is there, in a language broom checks, and not excluded."""
    return file.is_file() and bool(lang_of(file)) and not excluded(file)


def found_now(root: Path, files: List[Path]) -> Tuple[list, List[str]]:
    """What the checks of the day find anywhere in `files` (lint, types, and the smells that stop), with the tool
    notes. The heavy modules load only here."""
    from .checks import SLOW_PATH, run_checks
    from .gate import select

    issues, notes = run_checks(files, SLOW_PATH)
    now = select(issues, set(files), set(), whole=True)
    if setting("smells", root) != "off":
        from .smells import find_smells

        left = CLOCK.left()
        budget = SMELL_SECONDS if left is None else max(1.0, min(SMELL_SECONDS, left - MIN_SECONDS / 2))
        smells, more = find_smells(root, files, None, budget=budget)
        now += [s.issue() for s in smells if s.level != NIT]
        notes += more
    return now, notes


def still_there(row: dict, file: Path, now: dict) -> bool:
    """Whether the finding of the record `row` (in `file`) is among what a check found again (`now`, from `matches`):
    by its key; else at the same text of line, by file, tool and rule (a smell's message says how it compares, which a
    check again has nothing to compare with); else, for a line written before spots, by file, tool and rule alone; or
    a check that didn't run covers it."""
    group = (str(file), row.get("tool"), row.get("rule"))
    entry = {"file": str(file), "tool": row.get("tool"), "rule": row.get("rule")}
    if row["key"] in now["keys"] or any(ledger.covers(n, entry) for n in now["skipped"]):
        return True
    if row.get("spot"):
        return (*group, row["spot"]) in now["spots"]
    return group in now["groups"]


def matches(issues: Iterable, notes: List[str]) -> dict:
    """What `still_there` looks a finding up in: the keys, the (file, tool, rule, spot) and the (file, tool, rule) of
    `issues`, and the notes of the checks that didn't run."""
    from .gate import issue_key

    issues = list(issues)
    groups = [(str(i.file.resolve()), i.tool, i.rule) for i in issues]
    return {"keys": {issue_key(i) for i in issues}, "groups": set(groups),
            "spots": {(*g, ledger.spot(i.file, i.line)) for g, i in zip(groups, issues)},
            "skipped": [n for n in notes if n.startswith(ledger.SKIP_PREFIXES)]}


def recheck(root: Path, found: Dict[str, dict]) -> Dict[str, dict]:
    """Check the files of `found` (open findings of the record, by key) in the worktree `root` again, write a `fix`
    line for each that is gone, and give those still there. One whose file no check covers any more leaves with no
    line. With too little of the hook's time left, nothing is checked and all are still there."""
    files = {k: (root / str(r.get("file"))).resolve() for k, r in found.items()}
    here = {k: r for k, r in found.items() if covered(files[k])}
    left = CLOCK.left()
    if not here or (left is not None and left < MIN_SECONDS):
        return here
    now = matches(*found_now(root, sorted({files[k] for k in here})))
    gone = {k: r for k, r in here.items() if not still_there(r, files[k], now)}
    ledger.write(ledger.not_fixed_yet([ledger.line("fix", str(r.get("repo")), key=k, tool=r.get("tool"),
                                                   rule=r.get("rule"), file=r.get("file")) for k, r in gone.items()]))
    return {k: r for k, r in here.items() if k not in gone}


# ---------------------------------------------------------------- a session's start


def session_note(root: Path) -> Optional[str]:
    """What a session's start in the worktree `root` tells Claude of the findings still open in its repo, once their
    files were checked again; None when none is."""
    if setting("check_on", root) == "off":
        return None
    found = standing(str(main_worktree(root)))
    left = recheck(root, found) if found else {}
    if not left:
        return None
    rows = sorted(left.values(), key=lambda r: (not r["asked"], str(r.get("file")), r.get("line") or 0))
    n, put = len(rows), sum(1 for r in rows if r["asked"])
    asked_part = f", {put} of them put to the user" if put else ""
    labels = [place(r) + (" (asked)" if r["asked"] else "") for r in rows]
    return (f"broom: {n} finding{'' if n == 1 else 's'} that stopped a commit or a turn's end "
            f"{'is' if n == 1 else 'are'} still open in this repo{asked_part}: {named(labels)}. No fix or "
            "accept has ended them. Don't interrupt the user's task for this: fix them when it fits, and tell the "
            "user at a natural point. The next check of their file blocks on them again, where one can be accepted "
            "with a reason or put to the user.")


# ---------------------------------------------------------------- the prompt after a question


def due(d: Path, name: str) -> List[dict]:
    """The findings asked about in the session's file `name` (asked.DUE or asked.TOLD), by key, the last row of each."""
    return list({r["key"]: r for r in ledger.read(d / name) if r.get("key") and r.get("repo")}.values())


def still_open(rows: List[dict]) -> List[dict]:
    """Those of `rows` (asked about) that the record holds open, each with what the record says of it."""
    by_repo: Dict[str, Dict[str, dict]] = {}
    out = []
    for r in rows:
        repo = str(main_worktree(Path(r["repo"])))
        if repo not in by_repo:
            by_repo[repo] = standing(repo)
        if r["key"] in by_repo[repo]:
            out.append({**by_repo[repo][r["key"]], "at": r.get("at"), "why": r.get("why"), "root": r["repo"]})
    return out


def accept_command(rows: List[dict], cwd: Path) -> str:
    """The command that accepts what the user agreed to leave, with the repo's path where `cwd` isn't the repo."""
    roots = dict.fromkeys(str(r["root"]) for r in rows)
    return " and ".join("`broom known --accept \"<why>\" --agreed" + ("" if Path(root) == cwd else
                                                                      f" {shlex.quote(root)}") + "`" for root in roots)


def answer_text(rows: List[dict], cwd: Path) -> str:
    """What the prompt after a question tells Claude of the findings it asked about and that are still open."""
    questions = list(dict.fromkeys(str(r.get("why")) for r in rows))
    shown = ", ".join(f"{r.get('at')} {r.get('rule')}" for r in rows[:SHOWN])
    more = f", and {len(rows) - SHOWN} more" if len(rows) > SHOWN else ""
    n = len(rows)
    return (f"broom: this prompt holds the user's answer to your question ({' | '.join(questions)}) about {n} "
            f"finding{'' if n == 1 else 's'} still open: {shown}{more}. Fix {'it' if n == 1 else 'them'}, or if the "
            f"user agreed to leave {'it' if n == 1 else 'them'}, run {accept_command(rows, cwd)}.")


def hook_answer(data: dict) -> None:
    """The synchronous prompt hook, run only while a question waits (hooks/prompt.sh): tell Claude, in the turn that
    holds the user's answer, the findings it asked about that are still open, from the record; and leave them to the
    async prompt hook to check again."""
    from .turns import turn_dir

    d = asked.session_of(turn_dir(data))
    rows = still_open(due(d, asked.DUE))
    try:
        if rows:
            (d / asked.DUE).replace(d / asked.TOLD)
        else:
            (d / asked.DUE).unlink()
    except OSError:
        pass
    if rows:
        cwd = Path(data.get("cwd") or ".").resolve()
        emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": answer_text(rows, cwd)}})


def recheck_answered(d: Path) -> None:
    """The async prompt hook's part: check again the files of the findings the prompt told (or is about to), record
    what is gone as fixed, and tell Claude so on its next turn."""
    rows = due(d, asked.TOLD) or due(d, asked.DUE)
    gone: List[dict] = []
    by_root: Dict[str, List[dict]] = {}
    for r in still_open(rows):
        by_root.setdefault(r["root"], []).append(r)
    for root, group in by_root.items():
        found = {r["key"]: r for r in group}
        left = recheck(Path(root), found)
        gone += [r for k, r in found.items() if k not in left]
    try:
        (d / asked.TOLD).unlink()
    except OSError:
        pass
    if gone:
        emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": (
            f"broom: {len(gone)} of the findings you asked the user about {'is' if len(gone) == 1 else 'are'} gone "
            f"now, recorded as fixed or no longer checked: {named([place(r) for r in gone])}. Nothing to do for "
            f"{'it' if len(gone) == 1 else 'them'}.")}})

