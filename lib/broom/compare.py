"""`broom compare BASE`: what the work since a revision did to the smells, in numbers. The repo is measured as it is
now and as it was at BASE, each whole and with no base of its own; BASE is checked out into a temporary linked
worktree for that, which is removed again whatever happens. The smells of the two are matched as smells.py matches
versions: by file, kind and the function's name or the line's text, a renamed file by its old path. The report
as text is in compareview."""

from __future__ import annotations

import re
import shutil
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .diagnose import measure
from .gitutil import git, renamed, run
from .hotspots import churn_order, rank, score, severity
from .rowcache import forget
from .smells import Smell

CHECKOUT_SECONDS = 600  # a checkout of a big repo takes a while
# What a note about a tool says of the smells it measures: the notes name the binary, the smells carry the label of
# the measurer (`Smell.tool`): python (ruff and the parser), js (oxlint), go, swift, and the real-tree tools by name.
TOOL_LABELS = {"ruff": "python", "oxlint": "js", "node": "js", "golangci-lint": "go", "swiftlint": "swift"}


def resolve(repo: Path, rev: str) -> str:
    """The commit `rev` names; exits with a message when it names none."""
    out = git(["rev-parse", "--verify", "-q", f"{rev}^{{commit}}"], repo)
    if not out or not out.strip():
        raise SystemExit(f"broom: unknown revision {rev!r}")
    return out.strip()


@contextmanager
def checkout(repo: Path, sha: str) -> Iterator[Path]:
    """A detached linked worktree of `repo` at `sha` in a temporary directory, removed when the block ends, whatever
    happens in it: the worktree, its entry in git, and the rows the smell cache kept for its path."""
    tmp = Path(tempfile.mkdtemp(prefix="broom-compare-")).resolve()
    tree = tmp / "tree"
    try:
        rc, _, err = run(["git", "worktree", "add", "--detach", str(tree), sha], repo, timeout=CHECKOUT_SECONDS)
        if rc != 0:
            raise SystemExit(f"broom: can't check out {sha[:10]} to measure it: {err.strip() or 'git timed out'}")
        yield tree
    finally:
        rc, _, _ = run(["git", "worktree", "remove", "--force", str(tree)], repo, timeout=CHECKOUT_SECONDS)
        shutil.rmtree(tmp, ignore_errors=True)
        if rc != 0:  # a checkout that failed half way: git may still list it, and pruning drops what has no directory
            run(["git", "worktree", "prune"], repo)
        forget(tree)


def measure_at(repo: Path, sha: str) -> Tuple[List[Smell], List[str], Dict[str, int]]:
    """Every smell of the repo as it was at `sha`, the notes of that measuring, and the commits per file in the
    last commits up to `sha`, from a temporary checkout. A note that names the checkout names the repo instead."""
    with checkout(repo, sha) as tree:
        found, notes = measure(tree, [])
        churn, _, _ = churn_order(tree, "churn")
    return found, [n.replace(str(tree), str(repo)) for n in notes], churn


# ---------------------------------------------------------------- what can't be compared


def tools_in(note: str, labels: Set[str]) -> Set[str]:
    """The measurer labels (among `labels`) a note names, directly or through the binary it names."""
    words = set(re.findall(r"[\w-]+", note))
    return (labels & words) | {TOOL_LABELS[w] for w in words if w in TOOL_LABELS}


def uncomparable(before: List[Smell], after: List[Smell], notes: Tuple[List[str], List[str]]) -> Set[str]:
    """The measurers that ran in one measuring and not in the other (a note says so in one only): what they find
    can't be compared. A tool missing in both measurings is missing in both, so its absence is the same."""
    labels = {s.tool for s in before + after}
    lonely = set(notes[0]) ^ set(notes[1])
    return set().union(*(tools_in(n, labels) for n in lonely))


# ---------------------------------------------------------------- matching the smells of two versions


def rel_of(s: Smell) -> str:
    """A smell's file, from the root of the tree it was measured in."""
    return s.file.relative_to(s.repo).as_posix()


def key_of(rel: str, s: Smell) -> tuple:
    """What matches a smell across versions: the file, the kind, and the function or the text. A clone is named by
    the file it repeats and not by the line, which moves."""
    return rel, s.metric, s.key.rsplit(":", 1)[0] if s.metric == "duplicate_lines" else s.key


def pair_up(before: List[Smell], after: List[Smell], moved: Dict[str, str]
            ) -> Tuple[List[Smell], List[Smell], List[Tuple[Smell, Smell]]]:
    """The smells that are gone, those that are new, and the pairs that are one smell in both versions, as
    (before, after). `moved` maps a path at the base to the path it has now."""
    old: Dict[tuple, List[Smell]] = {}
    for s in before:
        old.setdefault(key_of(moved.get(rel_of(s), rel_of(s)), s), []).append(s)
    new: List[Smell] = []
    pairs: List[Tuple[Smell, Smell]] = []
    for s in after:
        same = old.get(key_of(rel_of(s), s))
        if same:
            pairs.append((same.pop(0), s))
        else:
            new.append(s)
    return [s for rows in old.values() for s in rows], new, pairs


def change_row(s: Smell, was: Optional[int], now: Optional[int]) -> dict:
    """One smell of a list: where it is, how it reads, and its size or count before and after (None where it isn't)."""
    return {"file": rel_of(s), "line": s.line, "smell": s.metric, "level": s.level, "text": s.text(),
            "before": was, "after": now}


def kind_rows(before: List[Smell], after: List[Smell]) -> List[dict]:
    """Per kind of smell: how many before, after, and the difference; the biggest kinds first."""
    was, now = Counter(s.metric for s in before), Counter(s.metric for s in after)
    rows = [{"smell": k, "before": was[k], "after": now[k], "change": now[k] - was[k]} for k in set(was) | set(now)]
    return sorted(rows, key=lambda r: (-max(r["before"], r["after"]), r["smell"]))


def triple(was: int, now: int) -> dict:
    """A count before and after, with the difference."""
    return {"before": was, "after": now, "change": now - was}


def summary_of(before: List[Smell], after: List[Smell]) -> dict:
    """The smells, those past the hard limit, the hints and the nits, before and after."""
    out = {}
    for name, levels in (("smells", None), ("severe", ("block",)), ("hints", ("hint",)), ("nits", ("nit",))):
        count = [sum(levels is None or s.level in levels for s in rows) for rows in (before, after)]
        out[name] = triple(*count)
    return out


def status_of(was: int, now: int) -> str:
    """How a hotspot moved: cleared, better, same or worse, from its weight of smells before and after."""
    if now == 0:
        return "cleared"
    if now == was:
        return "same"
    return "better" if now < was else "worse"


def hotspot_moves(before: List[Smell], after: List[Smell], churn: Dict[str, int], moved: Dict[str, str],
                  top: int) -> List[dict]:
    """How each of the `top` hotspots of the base moved: its smells before and after, and whether it got better. The
    hotspots are ranked as `broom smells` ranked them then, by churn when the base has history."""
    _, files = rank(before, churn, "churn" if churn else "smells")
    _, now_files = rank(after, {}, "smells")
    now = {f["file"]: f for f in now_files}
    rows = []
    for f in files[:top]:
        here = moved.get(f["file"], f["file"])
        n = now.get(here, {"severe": 0, "hints": 0, "nits": 0})
        rows.append({"file": f["file"], "now": here, "changes": f["changes"],
                     "severe": {"before": f["severe"], "after": n["severe"]},
                     "hints": {"before": f["hints"], "after": n["hints"]},
                     "nits": {"before": f["nits"], "after": n["nits"]},
                     "status": status_of(score(f["severe"], f["hints"], 0), score(n["severe"], n["hints"], 0))})
    return rows


# ---------------------------------------------------------------- the comparison


def signed(n: int) -> str:
    """A difference with its sign, `0` when there is none."""
    return f"{n:+d}" if n else "0"


def quote(rev: str, summary: dict, skipped: List[str]) -> str:
    """The line a person can quote: what the work since `rev` did, with the kinds that couldn't be compared."""
    smells, severe = summary["smells"], summary["severe"]
    line = (f"since {rev}: {smells['before']} smells -> {smells['after']} ({signed(smells['change'])}); "
            f"past the hard limit {severe['before']} -> {severe['after']}")
    return line + (f"; not comparable: {', '.join(skipped)}" if skipped else "")


def pair_row(pair: Tuple[Smell, Smell]) -> dict:
    """A smell that is in both versions, as the row of the list it is in: its size or count before and after."""
    return change_row(pair[1], pair[0].value, pair[1].value)


def changes(before: List[Smell], after: List[Smell], moved: Dict[str, str]) -> dict:
    """The smells that are gone, new, smaller and bigger, each list worst first. A smell is smaller or bigger when
    its size or count (a function's lines, the occurrences in a file) differs between the versions."""
    gone, new, pairs = pair_up(before, after, moved)
    pairs.sort(key=lambda p: severity(p[1]), reverse=True)
    return {"gone": [change_row(s, s.value, None) for s in sorted(gone, key=severity, reverse=True)],
            "new": [change_row(s, None, s.value) for s in sorted(new, key=severity, reverse=True)],
            "shrank": [pair_row(p) for p in pairs if p[1].value < p[0].value],
            "grew": [pair_row(p) for p in pairs if p[1].value > p[0].value]}


def compare(repo: Path, rev: str, top: int) -> dict:
    """The smells of the repo now against those at `rev`: per kind, which are gone, new, smaller and bigger, and how
    the `top` hotspots of `rev` moved. What a tool that ran in one measuring and not in the other finds is left out
    of all of it, and named in `not_comparable`. Exits when `rev` is unknown."""
    started = time.monotonic()
    sha = resolve(repo, rev)
    moved = {old: new for new, old in renamed(repo, [sha]).items()}
    after, notes_after = measure(repo, [])
    before, notes_before, churn = measure_at(repo, sha)
    skip = uncomparable(before, after, (notes_before, notes_after))
    skipped = sorted({s.metric for s in [*before, *after] if s.tool in skip})
    before, after = ([s for s in rows if s.tool not in skip] for rows in (before, after))
    summary = summary_of(before, after)
    return {"repo": str(repo), "base": rev, "base_commit": sha, "summary": summary, "kinds": kind_rows(before, after),
            **changes(before, after, moved), "hotspots": hotspot_moves(before, after, churn, moved, top),
            "not_comparable": {"tools": sorted(skip), "kinds": skipped},
            "notes": notes_after + [f"at {rev}: {n}" for n in notes_before if n not in notes_after],
            "quote": quote(rev, summary, skipped), "seconds": round(time.monotonic() - started, 1)}
