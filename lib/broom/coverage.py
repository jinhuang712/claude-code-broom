"""Test coverage, read from the report a project's own test run wrote: broom runs no tests. Four forms are read, told
apart by how the report starts: Cobertura XML (`coverage xml`, and what most tools can write), lcov (`lcov.info`), Go's
cover profile and coverage.py's JSON. The report is looked for at the usual places under the repo root (`PLACES`), and
the newest one wins. A file the report names is matched to a file of the repo, whatever folder the tests ran from.

`broom stats` shows the share of lines a test reached and the files with most lines none did; the check-up counts those
lines per file, so a report that got worse is told once. Without a report nothing is counted, and `broom stats` says how
to write one."""

from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .gitutil import git

PLACES = ("coverage.xml", "cobertura.xml", "coverage/coverage.xml", "coverage/cobertura-coverage.xml", "lcov.info",
          "coverage/lcov.info", "coverage.lcov", "coverage.out", "cover.out", "coverage.json")
MAX_BYTES = 32 * 1024 * 1024  # a larger report is left unread: a hook must not spend its seconds on one file
DAY = 86400
SLACK = 60  # a commit made within a minute after the report is the one the tests ran for: the report isn't behind it
GO_BLOCK = re.compile(r"^(.+):(\d+\.\d+,\d+\.\d+) (\d+) (\d+)$")
# How each language's usual test run writes a report broom reads.
HOW = {"py": "coverage run -m pytest && coverage xml", "go": "go test -coverprofile=coverage.out ./...",
       "js": "jest --coverage --coverageReporters=lcov  (vitest: --coverage --coverage.reporter=lcov)",
       "rust": "cargo llvm-cov --lcov --output-path lcov.info"}

Marks = Dict[str, Dict[str, Tuple[int, bool]]]  # per file as the report names it, per line or block: weight, reached
Lines = Dict[str, Tuple[int, int]]  # per file from the repo root: the lines a test reached, and all it could have


def mark(marks: Marks, name: str, key: str, weight: int, *, hit: bool) -> None:
    """Note one line or block of file `name`: reached when any entry for it says so, as reports repeat a file per run."""
    seen = marks.setdefault(name, {})
    seen[key] = (weight, hit or (key in seen and seen[key][1]))


def read_lcov(text: str) -> Tuple[Marks, List[str]]:
    """The lines of an lcov report: `SF:` names a file and each `DA:line,hits` under it one line."""
    marks: Marks = {}
    name = ""
    for row in text.splitlines():
        if row.startswith("SF:"):
            name = row[3:].strip()
        elif row.startswith("DA:") and name:
            line, _, hits = row[3:].partition(",")
            mark(marks, name, line, 1, hit=not hits.startswith("0"))
    return marks, []


def read_go(text: str) -> Tuple[Marks, List[str]]:
    """The blocks of a Go cover profile: `file:start,end statements count`, each block weighing its statements."""
    marks: Marks = {}
    for row in text.splitlines():
        m = GO_BLOCK.match(row)
        if m:
            mark(marks, m.group(1), m.group(2), int(m.group(3)), hit=m.group(4) != "0")
    return marks, []


def read_json(text: str) -> Tuple[Marks, List[str]]:
    """The lines of coverage.py's JSON report: `executed_lines` and `missing_lines` per file."""
    marks: Marks = {}
    files = json.loads(text).get("files")
    for name, entry in (files.items() if isinstance(files, dict) else ()):
        for key, hit in (("executed_lines", True), ("missing_lines", False)):
            for line in (entry.get(key) or () if isinstance(entry, dict) else ()):
                mark(marks, name, str(line), 1, hit=hit)
    return marks, []


def read_cobertura(text: str) -> Tuple[Marks, List[str]]:
    """The lines of a Cobertura XML report with its `<source>` folders, which the file names are relative to. A report
    that declares entities is refused: it is no coverage tool's output, and expanding them can take all the memory."""
    if "<!ENTITY" in text:
        raise ValueError("entities declared")
    root = ET.fromstring(text)
    marks: Marks = {}
    for cls in root.iter("class"):
        name = cls.get("filename") or ""
        for line in (cls.iter("line") if name else ()):
            mark(marks, name, line.get("number") or "", 1, hit=(line.get("hits") or "0") != "0")
    return marks, [s.text.strip() for s in root.iter("source") if s.text and s.text.strip()]


def parse(text: str) -> Tuple[Marks, List[str]]:
    """The marks of a report and the folders its names are relative to, by the form its first characters show."""
    start = text.lstrip()[:16]
    if start.startswith("<"):
        return read_cobertura(text)
    if start.startswith("mode:"):
        return read_go(text)
    if start.startswith("{"):
        return read_json(text)
    return read_lcov(text)


def locate(root: str, name: str, sources: List[str]) -> Optional[str]:
    """The file of the repo at `root` that a report calls `name`, as a path from the root: the name itself, the name
    under one of the report's `sources`, or the longest end of the name that is a file here. That last form matches
    a path from another machine and Go's import path. None when the repo has no such file."""
    for candidate in (name, *(os.path.join(source, name) for source in sources)):
        full = os.path.realpath(os.path.join(root, candidate))
        if full.startswith(root + os.sep) and os.path.isfile(full):
            return os.path.relpath(full, root).replace(os.sep, "/")
    parts = Path(name).parts
    for i in range(1, len(parts)):
        rest = "/".join(parts[i:])
        if os.path.isfile(os.path.join(root, rest)):
            return rest
    return None


def report_path(repo: Path) -> Optional[Path]:
    """The coverage report of the repo: the one written last among `PLACES`, None when there is none."""
    found = [p for p in (repo / place for place in PLACES) if p.is_file()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def lines_of(repo: Path, report: Path) -> Optional[Lines]:
    """Per file of the repo, the lines a test reached and all the report counts. None for a report that is too large or
    that can't be read as any of the four forms."""
    try:
        if report.stat().st_size > MAX_BYTES:
            return None
        marks, sources = parse(report.read_text(errors="replace"))
    except (OSError, ValueError, ET.ParseError):
        return None
    root = os.path.realpath(repo)
    out: Lines = {}
    for name, seen in marks.items():
        rel = locate(root, name, sources)
        if rel:
            reached, total = out.get(rel, (0, 0))
            out[rel] = (reached + sum(w for w, hit in seen.values() if hit), total + sum(w for w, _ in seen.values()))
    return out


def missed(repo: Path, code: Set[str]) -> Optional[Dict[str, int]]:
    """The check-up's counter: per file among `code`, the lines the report says no test reached. None without a
    report that can be read, as nothing then says how many there are."""
    report = report_path(repo)
    lines = lines_of(repo, report) if report else None
    if lines is None:
        return None
    return {rel: total - reached for rel, (reached, total) in lines.items() if rel in code and total > reached}


def percent(reached: int, total: int) -> int:
    """The share of `total` that `reached` is, in whole percent, rounded down so that 100 means every line."""
    return 100 * reached // total if total else 100


def how_to(langs: Iterable[str]) -> List[str]:
    """A command per language among `langs` whose usual test run can write a report broom reads."""
    return [HOW[lang] for lang in sorted(set(langs)) if lang in HOW]


def section(repo: Path, code: Dict[str, str], top: int) -> dict:
    """What `broom stats` says of coverage for the files of `code` (path to language, tests left out): the report, its
    age and whether it is older than the last commit, the lines reached of all, how many files no test reaches at
    all, and the `top` files with most lines not reached. Without a report, `how`: the commands that write one."""
    report = report_path(repo)
    if report is None:
        return {"report": None, "how": how_to(code.values())}
    name = report.relative_to(repo).as_posix()
    lines = lines_of(repo, report)
    if lines is None:
        return {"report": name, "unread": True}
    mine = {rel: counts for rel, counts in lines.items() if rel in code}
    written = report.stat().st_mtime
    last = git(["log", "-1", "--format=%ct"], repo) or ""
    worst = sorted(mine.items(), key=lambda kv: (kv[1][0] - kv[1][1], kv[0]))[:top]
    reached, total = sum(r for r, _ in mine.values()), sum(t for _, t in mine.values())
    return {"report": name, "unread": False, "age_days": int((time.time() - written) // DAY),
            "behind": last.strip().isdigit() and written < int(last) - SLACK, "lines": total, "reached": reached,
            "percent": percent(reached, total), "files": len(mine),
            "unreached_files": sum(1 for r, t in mine.values() if t and not r),
            "least": [{"file": rel, "lines": t, "missed": t - r, "percent": percent(r, t)}
                      for rel, (r, t) in worst if t > r]}
