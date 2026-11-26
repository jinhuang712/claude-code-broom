"""What `broom stats` and the hotspots ask git: which files changed together in the last commits, one `git log` for
the lot."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .gitutil import git, run

CHURN_COMMITS = 500  # how many of the last commits a file's changes are counted over
BIG_COMMIT = 30  # a commit touching more files than this is a move or a sweep, not a change that went together
LOG_SECONDS = 60


def top_counts(counts: Dict[object, int], top: int) -> List[Tuple[object, int]]:
    """The `top` highest counts, highest first, ties by name."""
    return sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[:top]


def log(repo: Path, commits: int) -> Optional[List[List[str]]]:
    """The files of each of the last `commits` commits up to HEAD, merges left out; None when git can't say (no commit
    yet, or git gave up)."""
    rc, out, _ = run(["git", "-c", "core.quotepath=off", "log", "-n", str(commits), "--name-only",
                      "--no-renames", "--no-merges", "--format=%x01"], repo, timeout=LOG_SECONDS)
    if rc != 0:
        return None
    return [[n for n in chunk.splitlines() if n] for chunk in out.split("\x01")[1:]]


def commits_per_file(repo: Path, commits: int) -> Optional[Counter]:
    """How many of the last `commits` commits touched each file, from the same `git log` the history section
    reads; None when git can't say."""
    found = log(repo, commits)
    return None if found is None else Counter(f for files in found for f in set(files))


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


def history(repo: Path, kept: Set[str], last: int, top: int, note: Optional[str]) -> dict:
    """The history section: `commits`, the number found among the last `last` commits, the `top` most changed of the
    `kept` files and the `top` pairs that changed together most often. `note` is why the files can't be counted, if they can't; when git has too
    little to say, the note says what is missing."""
    out: dict = {"last_commits": last, "commits": 0, "files": [], "pairs": [], "note": note}
    if note:
        return out
    commits = log(repo, last)
    if commits is None:
        return {**out, "note": "no history yet: git log found no commit"}
    per_file, pairs = changes(commits, kept)
    out.update(commits=len(commits), files=[{"file": f, "commits": n} for f, n in top_counts(per_file, top)],
               pairs=[{"files": list(p), "commits": n} for p, n in top_counts(pairs, top)])
    if not commits:
        out["note"] = "no commits to count"
    elif shallow(repo):
        out["note"] = "a shallow clone: the history before its cut is missing"
    return out
