"""The check-up: a look at the whole repo for rot, which gets worse without any one change being at fault. It keeps
the counters of `LABELS` (lint suppressions, skipped tests, TODO comments older than `OLD_DAYS` days, dead-code
findings, public code with no doc comment, calls to deprecated APIs, duplicate test blocks, lines no test reaches)
per file, and the numbers of the last check-up per repo, in broom's data directory. The session scan runs it in the
background after the smell scan, and tells Claude, once, of each counter that is higher than at the last check-up,
with the files that added to it. It never blocks and takes only what is cheap: the one pass over the files `broom
stats` makes, a bounded `git blame`, the coverage report a test run left, and the counts the smell scan already has.

`broom diagnose` lists every counter, grown or not (`section`); it never changes the record."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__, coverage
from .config import CHECKUP, DEAD_CODE, repo_config, setting
from .gitutil import CLOCK, main_worktree
from .state import DATA_ROOT, load_json, short_hash, update_json
from .stats import collect
from .statscan import Facts
from .statsgit import DAY, OLD_DAYS, blame
from .testrot import DUPLICATE_TESTS

RECORDS = DATA_ROOT / "checkup"
UNCOVERED = "uncovered_lines"
FILES_NAMED = 3  # how many files a line of the note names
MIN_SECONDS = 6  # a hook with less time left than this leaves the check-up to the next session
LABELS = {"suppressions": "lint suppressions", "skipped_tests": "skipped tests",
          "old_todos": f"TODO comments older than {OLD_DAYS} days", DEAD_CODE: "dead-code findings",
          "missing_docs": "public code with no doc comment", "deprecated_api": "calls to deprecated APIs",
          DUPLICATE_TESTS: "duplicate test blocks", UNCOVERED: "lines no test reaches, by the coverage report"}
# Counted by the smell scan, not by the pass over the files.
SMELL_COUNTERS = (DEAD_CODE, "missing_docs", "deprecated_api", DUPLICATE_TESTS)
TELL = "At a natural point tell the user; don't interrupt their task."

Counts = Dict[str, int]  # per file: the files that hold any, by path from the repo root
Counted = Dict[str, Optional[Counts]]  # per counter; None for one that couldn't be counted
Row = Tuple[str, int, int, List[str]]  # a counter that grew: its name, the value before and now, the files that added


def record_path(repo: Path) -> Path:
    """Where the numbers of the last check-up are kept: one record for the repo, whichever of its worktrees asks."""
    return RECORDS / f"{short_hash(str(main_worktree(repo)))}.json"


def is_off(repo: Path) -> bool:
    """Whether the repo turned the check-up off: `smells` at off, or `checkup` among `smells_off` in .broom.json."""
    off = repo_config(repo).get("smells_off")
    return setting("smells", repo) == "off" or (isinstance(off, list) and CHECKUP in off)


def old_todos(repo: Path, facts: List[Facts]) -> Optional[Counts]:
    """Per file, the TODO comments git blame dates more than `OLD_DAYS` days back: at most `BLAME_LINES` lines are
    asked, the files with most first. None when the hook's time ran out, as the blame then answered nothing."""
    order = sorted((f for f in facts if f.todos), key=lambda f: (-len(f.todos), f.rel))
    cutoff = time.time() - OLD_DAYS * DAY
    written = blame(repo, [(f.rel, f.todos) for f in order]).written
    old: Counts = dict(Counter(rel for rel, _, when in written if when < cutoff))
    return None if CLOCK.left() == 0 else old


def counters(repo: Path, facts: List[Facts], from_smells: Optional[Counted]) -> Counted:
    """Every counter, per file, as the repo is now. `from_smells` holds those the smell scan counted (hotspots.
    smell_counts); a counter is None when it couldn't be counted: it is then neither compared nor recorded."""
    now: Counted = {
        "suppressions": {f.rel: len(f.suppressions) for f in facts if f.suppressions},
        "skipped_tests": {f.rel: f.skipped for f in facts if f.skipped},
        "old_todos": old_todos(repo, facts),
        UNCOVERED: coverage.missed(repo, {f.rel for f in facts if not f.test})}
    return {**now, **{name: (from_smells or {}).get(name) for name in SMELL_COUNTERS}}


def total(counts: Optional[Counts]) -> Optional[int]:
    """The sum over the files, None for a counter that couldn't be counted."""
    return None if counts is None else sum(counts.values())


def added_by(was: Counts, now: Counts) -> List[str]:
    """The files whose count rose since `was`, the ones that rose most first, then by name."""
    rose = {rel: n - was.get(rel, 0) for rel, n in now.items() if n > was.get(rel, 0)}
    return [rel for rel, _ in sorted(rose.items(), key=lambda kv: (-kv[1], kv[0]))]


def grown(before: Counted, now: Counted) -> List[Row]:
    """(counter, value at the last check-up, value now, files that added to it) for each counter that rose. A counter
    with no number on either side has nothing to compare."""
    out = []
    for name in LABELS:
        was, here = before.get(name), now.get(name)
        if was is not None and here is not None and total(here) > total(was):
            out.append((name, sum(was.values()), sum(here.values()), added_by(was, here)))
    return out


def line_of(row: Row) -> str:
    """`lint suppressions 6 -> 9 (a.py, b.py)`: a counter that grew, with up to `FILES_NAMED` files that added."""
    name, was, here, files = row
    more = f" and {len(files) - FILES_NAMED} more" if len(files) > FILES_NAMED else ""
    return f"{LABELS[name]} {was} -> {here} ({', '.join(files[:FILES_NAMED])}{more})"


def note_of(rows: List[Row]) -> str:
    """What Claude is told: one clause per counter that grew."""
    return f"broom check-up: {'; '.join(line_of(r) for r in rows)}. {TELL}"


def check_up(repo: Path, from_smells: Optional[Counted]) -> Optional[str]:
    """Count the repo's rot, compare it with the last check-up, keep the new numbers as the baseline, and return the
    note for what grew. None the first time and after an update of broom, when the numbers became the baseline silently, when nothing grew (a
    number that fell is kept as it is), and when the repo turned the check-up off. A counter that couldn't be
    counted keeps the number it had."""
    if is_off(repo):
        return None
    now = counters(repo, collect(repo, []), from_smells)
    told: List[str] = []

    def keep(record: dict) -> dict:
        before = record.get("counters")
        # Numbers another version of broom took may count other things (a rule added, a marker narrowed): they
        # are no measure of what the code did since, so this version's numbers start over as the baseline.
        rows = grown(before, now) if before and record.get("version") == __version__ else []
        if rows:
            told.append(note_of(rows))
        counted = {name: counts for name, counts in now.items() if counts is not None}
        return {"at": time.strftime("%Y-%m-%d"), "version": __version__, "counters": {**(before or {}), **counted}}

    update_json(record_path(repo), {}, keep)
    return told[0] if told else None


def check_up_time(repo: Path, data: Optional[dict]) -> Optional[str]:
    """`check_up` from a smell scan's summary `data`, or None when there is none (no commit, too many files) or the
    hook has too little time left."""
    left = CLOCK.left()
    if data is None or (left is not None and left < MIN_SECONDS):
        return None
    return check_up(repo, data.get("counts"))


# ---------------------------------------------------------------- the diagnosis


def row_of(name: str, was: Optional[Counts], now: Optional[Counts]) -> dict:
    """One counter of the diagnosis: its value now and at the last check-up (None when unknown), whether it grew and
    the files that added to it."""
    before, here = total(was), total(now)
    grew = before is not None and here is not None and here > before
    files = added_by(was, now)[:FILES_NAMED] if grew and was is not None and now is not None else []
    return {"counter": name, "label": LABELS[name], "now": here, "was": before, "grew": grew, "files": files}


def section(repo: Path, facts: List[Facts], from_smells: Optional[Counted], *, narrowed: bool) -> dict:
    """The diagnosis's Check-up section: every counter, now and at the last check-up, grown or not. A diagnosis
    narrowed to some paths counts only those, so it has no last check-up to set against. It never writes the record."""
    if is_off(repo):
        return {"off": True, "narrowed": narrowed, "last": None, "counters": []}
    record = {} if narrowed else load_json(record_path(repo), {})
    before = record.get("counters") or {}
    now = counters(repo, facts, from_smells)
    return {"off": False, "narrowed": narrowed, "last": record.get("at"),
            "counters": [row_of(name, before.get(name), now.get(name)) for name in LABELS]}
