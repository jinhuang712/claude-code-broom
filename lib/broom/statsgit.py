"""The two questions `broom stats` asks git: which files changed together in the commits of the last days (one `git log`
for the lot) and how old some lines are (`git blame`, for a bounded number of them)."""

from __future__ import annotations

import re
import time
from collections import Counter
from itertools import chain, combinations
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .gitutil import git, run

OLD_DAYS = 180  # a note to self this old, by git blame, is one nobody came back to
BLAME_LINES = 200  # at most this many lines are blamed: one git process per file that holds one
BIG_COMMIT = 30  # a commit touching more files than this is a move or a sweep, not a change that went together
LOG_SECONDS = 60
DAY = 86400


def top_counts(counts: Dict[object, int], top: int) -> List[Tuple[object, int]]:
    """The `top` highest counts, highest first, ties by name."""
    return sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[:top]


def old_lines(repo: Path, files: List[Tuple[str, List[int]]], days: int) -> Tuple[int, int, bool]:
    """Ask `git blame` when the given lines were written: `files` is (path, line numbers) pairs. Returns how many lines
    were blamed, how many of those are older than `days` days and whether the cap (`BLAME_LINES`) left lines out. A
    file git doesn't know (untracked, so new) is not blamed."""
    cutoff = time.time() - days * DAY
    blamed = old = 0
    left, cut = BLAME_LINES, False
    for rel, lines in files:
        cut = cut or len(lines) > left
        asked = lines[:left]
        if not asked:
            break
        ranges = chain.from_iterable(("-L", f"{n},{n}") for n in asked)
        out = git(["blame", "--line-porcelain", *ranges, "--", rel], repo)
        if out is None:
            continue
        times = [int(t) for t in re.findall(r"^author-time (\d+)$", out, re.M)]
        blamed += len(times)
        old += sum(t < cutoff for t in times)
        left -= len(asked)
    return blamed, old, cut


def log(repo: Path, days: int) -> Optional[List[List[str]]]:
    """The files of each commit of the last `days` days, merges left out; None when git can't say (no commit yet, or
    git gave up)."""
    rc, out, _ = run(["git", "-c", "core.quotepath=off", "log", f"--since={days} days ago", "--name-only",
                      "--no-renames", "--no-merges", "--format=%x01"], repo, timeout=LOG_SECONDS)
    if rc != 0:
        return None
    return [[n for n in chunk.splitlines() if n] for chunk in out.split("\x01")[1:]]


def changes(commits: List[List[str]], kept: Set[str]) -> Tuple[Counter, Counter]:
    """How often each of the `kept` files changed, and how often each pair of them changed in one commit. A commit that
    touches more than `BIG_COMMIT` files counts for the first and not the second."""
    per_file: Counter = Counter()
    pairs: Counter = Counter()
    for files in commits:
        mine = sorted(set(files) & kept)
        per_file.update(mine)
        if len(files) <= BIG_COMMIT:
            pairs.update(combinations(mine, 2))
    return per_file, pairs


def shallow(repo: Path) -> bool:
    """Whether the repo is a shallow clone, whose history stops at the cut."""
    return (git(["rev-parse", "--is-shallow-repository"], repo) or "").strip() == "true"


def history(repo: Path, kept: Set[str], days: int, top: int, note: Optional[str]) -> dict:
    """The history section: `commits` in the last `days` days, the `top` most changed of the `kept` files and the `top`
    pairs that changed together most often. `note` is why the files can't be counted, if they can't; when git has too
    little to say, the note says what is missing."""
    out: dict = {"days": days, "commits": 0, "files": [], "pairs": [], "note": note}
    if note:
        return out
    commits = log(repo, days)
    if commits is None:
        return {**out, "note": "no history yet: git log found no commit"}
    per_file, pairs = changes(commits, kept)
    out.update(commits=len(commits), files=[{"file": f, "commits": n} for f, n in top_counts(per_file, top)],
               pairs=[{"files": list(p), "commits": n} for p, n in top_counts(pairs, top)])
    if not commits:
        out["note"] = f"no commits in the last {days} days"
    elif shallow(repo):
        out["note"] = "a shallow clone: the history before its cut is missing"
    return out
