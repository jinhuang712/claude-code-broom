"""Code smells: long functions and files, many parameters, deep nesting, high complexity, nested ternaries.

They are measured against broom's own limits, apart from the project's lint config, so one bar holds in every
repo; `.broom.json` can move it. Only what a change made worse counts: each file is measured as it is and as it
was at the base revision, and a finding counts when the change pushed it past a limit, or grew it while past
the hard one. Past the soft limit it is a hint, past the hard limit a block. Legacy code a change leaves as it
was never comes up.
"""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .checks import Issue
from .common import SMELL_LIMITS, git, repo_config, setting
from .gate import issue_key
from .measure import SMELL_EXTS, Limits, Raw, measure

DESCRIBE = {
    "function_lines": "{key} is {value} lines long",
    "file_lines": "the file is {value} lines long",
    "params": "{key} takes {value} parameters",
    "nesting": "blocks nest {value} levels deep",
    "complexity": "{key} has complexity {value}",
    "nested_ternary": "a ternary nests inside another",
}
HINTS_SHOWN = 10


@dataclass
class Smell:
    repo: Path
    file: Path
    line: int
    metric: str
    key: str
    value: int
    was: Optional[int]
    tool: str
    level: str  # "hint" past the soft limit, "block" past the hard one
    limit: int

    def text(self) -> str:
        what = DESCRIBE[self.metric].format(key=self.key, value=self.value)
        bar = f"hard limit {self.limit}" if self.level == "block" else f"over {self.limit}"
        how = "new" if self.was is None else f"was {self.was}"
        return f"{what} ({bar}; {how})"

    def issue(self) -> Issue:
        return Issue("smells", self.repo, self.file, self.line, 0, self.metric, self.text(),
                     severe=self.level == "block")


def limits(repo: Path) -> Limits:
    """broom's limits, with any the repo's .broom.json `limits` sets: {"function_lines": [50, 100], ...}."""
    merged = dict(SMELL_LIMITS)
    for name, pair in (repo_config(repo).get("limits") or {}).items():
        if name in merged and isinstance(pair, list) and len(pair) == 2 and all(isinstance(n, int) for n in pair):
            merged[name] = (pair[0], pair[1])
    return merged


# ---------------------------------------------------------------- comparing versions


LEVELS = ("", "hint", "block")


def level(value: int, limit: Tuple[int, int]) -> str:
    soft, hard = limit
    return "block" if value > hard else "hint" if value > soft else ""


def made_worse(value: int, old: Optional[int], limit: Tuple[int, int]) -> bool:
    """Pushed past a limit, or grown while past the hard one. Growth below that is noise: a 600-line file that
    gains a line was already over 400, and saying so on every edit teaches Claude to ignore broom."""
    was = level(old, limit) if old is not None else ""
    now = level(value, limit)
    return LEVELS.index(now) > LEVELS.index(was) or (now == "block" and old is not None and value > old)


def compare(now: List[Raw], before: Optional[List[Raw]], lim: Limits, repo: Path) -> List[Smell]:
    """`before` is None to report every finding (a whole-repo sweep), else the base version's findings."""
    was = {(r.rel, r.metric, r.key): r.value for r in before or []}
    out = []
    for r in now:
        old = was.get((r.rel, r.metric, r.key))
        at = level(r.value, lim[r.metric])
        if at and (before is None or made_worse(r.value, old, lim[r.metric])):
            limit = lim[r.metric][1] if at == "block" else lim[r.metric][0]
            out.append(Smell(repo, repo / r.rel, r.line, r.metric, r.key, r.value, old, r.tool, at, limit))
    return sorted(out, key=lambda s: (s.level != "block", str(s.file), s.line))


def find_smells(repo: Path, files: List[Path], base: Optional[str]) -> Tuple[List[Smell], List[str]]:
    """Smells in `files` that are new or worse than at `base`; every smell when `base` is None."""
    rels = []
    for f in files:
        try:
            rel = str(f.resolve().relative_to(repo))
        except ValueError:
            continue
        if f.suffix in SMELL_EXTS and f.is_file():
            rels.append(rel)
    if not rels:
        return [], []
    lim, notes = limits(repo), []
    now_text = {rel: (repo / rel).read_text(errors="replace") for rel in rels}
    old_text = None
    if base:
        old_text = {rel: text for rel in rels if (text := git(["show", f"{base}:{rel}"], repo)) is not None}
    with tempfile.TemporaryDirectory(prefix="broom-smells-") as tmp, ThreadPoolExecutor(2) as pool:
        now = pool.submit(measure, Path(tmp) / "now", now_text, lim, repo, notes)
        before = pool.submit(measure, Path(tmp) / "before", old_text, lim, repo, []) if old_text else None
        found = compare(now.result(), before.result() if before else ([] if base else None), lim, repo)
    return found, list(dict.fromkeys(notes))


def gate_smells(repo: Path, files: List[Path], known: set, base: str = "HEAD"
                ) -> Tuple[List[Issue], List[Smell], List[str]]:
    """For the hooks: the smells that block (as issues), the hints, and notes. Known ones are left out."""
    if setting("smells", repo) == "off":
        return [], [], []
    found, notes = find_smells(repo, files, base)
    blocks = [s.issue() for s in found if s.level == "block"]
    hints = [s for s in found if s.level == "hint" and issue_key(s.issue()) not in known]
    return [i for i in blocks if issue_key(i) not in known], hints, notes


def hint_text(hints: List[Smell]) -> str:
    shown = "; ".join(f"{s.file.relative_to(s.repo)}:{s.line} {s.text()}" for s in hints[:HINTS_SHOWN])
    more = f"; and {len(hints) - HINTS_SHOWN} more" if len(hints) > HINTS_SHOWN else ""
    return f"broom: {len(hints)} code smell(s) this change made worse; clean them up now: {shown}{more}"
