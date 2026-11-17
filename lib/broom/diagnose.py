"""`broom diagnose`: the whole repo measured once, with no time cut, as data. It composes what exists: the smells
(`find_smells` with no base and no budget, so a repo of any size is read in full) ranked as `broom smells` ranks
them, the four sections of `broom stats` and the check-up's counters. The report a person reads is in diagnoseview."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Tuple

from .checkup import section as checkup_section
from .gate import note_text
from .hotspots import CHURN_DAYS, churn_order, rank, repo_files, smell_counts, smell_row
from .smell import Scan, Smell
from .smells import find_smells
from .stats import collect, report as stats_report
from .testrot import duplicate_rows
from .toolchain import lang_of


def measure(repo: Path, paths: List[Path]) -> Tuple[Scan, List[str]]:
    """Every smell in the repo or in `paths`, and the notes: no base, so nothing is left out for being old, and no
    time budget, so the tools that run in the real tree run to the end. There is no limit on the files."""
    return find_smells(repo, repo_files(repo, paths), None)


def by_smell(repo: Path, ordered: List[Smell]) -> List[dict]:
    """Per kind of smell: how many there are, how many are past the hard limit and the worst one. `ordered` is the
    smells worst first; the kinds with most past the hard limit come first."""
    groups: Dict[str, List[Smell]] = {}
    for s in ordered:
        groups.setdefault(s.metric, []).append(s)
    rows = [{"smell": kind, "count": len(rows), "severe": sum(s.level == "block" for s in rows),
             "worst": smell_row(repo, rows[0])} for kind, rows in groups.items()]
    return sorted(rows, key=lambda r: (-r["severe"], -r["count"], r["smell"]))


def by_language(found: List[Smell]) -> List[dict]:
    """Per language: the smells, how many are past the hard limit and how many are hints."""
    groups: Dict[str, List[Smell]] = {}
    for s in found:
        groups.setdefault(lang_of(s.file) or s.file.suffix, []).append(s)
    rows = [{"language": lang, "count": len(rows), "severe": sum(s.level == "block" for s in rows),
             "hints": sum(s.level == "hint" for s in rows)} for lang, rows in groups.items()]
    return sorted(rows, key=lambda r: (-r["severe"], -r["count"], r["language"]))


def diagnose(repo: Path, paths: List[Path], top: int, days: int = CHURN_DAYS) -> dict:
    """The diagnosis of the repo, or of `paths`: the smells by kind and by language, the `top` hotspots by churn
    over the last `days` days, every smell, the tools that were missing, the four `stats` sections and the check-up's
    counters. `by` is the order the hotspots really have: by churn needs history."""
    started = time.monotonic()
    churn, order, history_notes = churn_order(repo, "churn", days)
    found, notes = measure(repo, paths)
    ordered, files = rank(found, churn, order)
    facts = collect(repo, paths)  # read once, for the stats sections and the check-up's counters
    stats = stats_report(repo, paths, top, days, facts)
    severe = sum(s.level == "block" for s in found)
    lines = stats["size"]["total"]
    summary = {"files": stats["files"], "lines": lines["lines"] + lines["test_lines"], "smells": len(found),
               "severe": severe, "hints": len(found) - severe, "seconds": round(time.monotonic() - started, 1)}
    return {"repo": str(repo), "paths": stats["paths"], "summary": summary, "by_smell": by_smell(repo, ordered),
            "by_language": by_language(found), "by": order, "hotspots": files[:top],
            "smells": [smell_row(repo, s) for s in ordered], "duplicate_tests": duplicate_rows(found.duplicate_tests),
            "missing_tools": [note_text(n) for n in notes if n.startswith("missing:")],
            "notes": [note_text(n) for n in notes if not n.startswith("missing:")] + history_notes, "stats": stats,
            "checkup": checkup_section(repo, facts, smell_counts(repo, found, notes), narrowed=bool(paths))}
