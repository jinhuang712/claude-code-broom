"""Duplicate and dead code, found by jscpd 5. Both need the whole repo: new code that repeats old code anywhere,
or code nothing anywhere uses. For duplicates, a base revision makes jscpd scan that tree too and mark the
clones the base didn't have; dead code (JavaScript, TypeScript and Python) leaves out tests and entry points."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .codelines import Lines, code_lines
from .gitutil import git, run, worktrees

SIDES = ("firstFile", "secondFile")  # the two copies in one of jscpd's clones
FORMATS = "javascript,typescript,jsx,tsx,python,go,swift,rust,css,scss,less"
TIMEOUT = 120


@dataclass
class Clone:
    """A duplicated block: where it is (`rel`, `line`), its copy (`other`, `other_line`), its size on each side, and if
    it is new. A size is in code lines (decision 039): jscpd counts the comment and blank lines of a block too, and
    its two sides may hold different ones."""
    rel: str
    line: int
    other: str
    other_line: int
    lines: int  # the code lines of its side's span
    new: bool  # absent at the base revision
    other_lines: int = 0  # the code lines of the copy's span


@dataclass
class Unused:
    """An unused symbol or file jscpd found: where it is (`rel`, `line`), and what it is, e.g. an export."""
    rel: str
    line: int
    what: str  # "export `name`", "symbol `name`", "import `name`", "this file", ...


def run_jscpd(repo: Path, args: List[str], report: str, skip_dirs: List[str], notes: List[str]) -> Optional[dict]:
    """jscpd's JSON report for `args` over the repo, or None with a note when it is missing or fails."""
    exe = shutil.which("jscpd")
    if not exe:
        notes.append("missing:jscpd (npm i -g jscpd), so duplicate and dead code aren't measured")
        return None
    skipped = [f"**/{d}/**" for d in skip_dirs] + [f"{w}/**" for w in nested_worktrees(repo)]
    with tempfile.TemporaryDirectory(prefix="broom-jscpd-") as out:
        cmd = [exe, *args, "-r", "json", "-o", out, "--no-tips", "-s", "-i", ",".join(skipped), "."]
        rc, _, err = run(cmd, repo, timeout=TIMEOUT)
        if rc is None:
            notes.append("timeout:jscpd")
            return None
        try:
            return json.loads((Path(out) / report).read_text())
        except (OSError, ValueError):
            notes.append(failure_note(err))
            return None


def nested_worktrees(repo: Path) -> List[str]:
    """The linked worktrees of the repo that sit inside `repo`, as paths relative to it. jscpd reads the folder and
    not git, so each would read as a copy of the whole repo."""
    here = repo.resolve()
    out = []
    for w in worktrees(here):
        try:
            rel = w.relative_to(here)
        except ValueError:
            continue
        if rel.parts:
            out.append(rel.as_posix())
    return out


def failure_note(err: str) -> str:
    """What jscpd said when it failed. Only an option it doesn't know means an older jscpd: a missing git ref
    once read as `version 5 or later needed`."""
    said = (err.strip().splitlines() or [""])[-1][:160]
    old = re.search(r"unknown (option|argument)|unexpected argument", err, re.I)
    return f"jscpd failed{' (version 5 or later needed)' if old else ''}: {said or 'no report'}"


def find_clones(repo: Path, base: Optional[str], min_lines: int, skip_dirs: List[str],
                notes: List[str]) -> List[Clone]:
    """Clones across the repo; with `base`, the ones `base` lacked are new. A base git can't resolve (a repo with
    no commit yet) gives no baseline, so no clone counts as new."""
    known = base is not None and git(["rev-parse", "--verify", "-q", f"{base}^{{commit}}"], repo) is not None
    args = ["-f", FORMATS, "--min-lines", str(min_lines), *(["--baseline-from-ref", base] if known else [])]
    found = (run_jscpd(repo, args, "jscpd-report.json", skip_dirs, notes) or {}).get("duplicates", [])
    code = code_lines(read_texts(repo, {d[side]["name"] for d in found for side in SIDES}), notes, repo)
    return [Clone(d["firstFile"]["name"], int(d["firstFile"]["start"]), d["secondFile"]["name"],
                  int(d["secondFile"]["start"]), code_in(code, d["firstFile"]), bool(d.get("isNew")),
                  code_in(code, d["secondFile"])) for d in found]


def read_texts(repo: Path, rels: Iterable[str]) -> Dict[str, str]:
    """The text of each of the files `rels` of the repo that can be read."""
    out = {}
    for rel in rels:
        try:
            out[rel] = (repo / rel).read_text(errors="replace")
        except OSError:
            pass
    return out


def code_in(code: Lines, side: dict) -> int:
    """The code lines in the span jscpd gives for one side of a clone (its file, first and last line); every line of
    the span for a file whose code lines weren't read."""
    first, last = int(side["start"]), int(side["end"])
    lines = code.get(side["name"])
    return last - first + 1 if lines is None else sum(first <= n <= last for n in lines)


def find_unused(repo: Path, skip_dirs: List[str], notes: List[str]) -> List[Unused]:
    """The dead code jscpd reports for the repo, as Unused rows; a jscpd that can't run adds a note and gives none."""
    found = (run_jscpd(repo, ["--dead-code"], "basta-report.json", skip_dirs, notes) or {}).get("findings", [])
    out = []
    for f in found:
        kind = str(f.get("category", "")).replace("unused-", "")
        what = "this file" if kind == "file" else f"{kind} `{f.get('name', '')}`"
        out.append(Unused(f.get("path", ""), int((f.get("start") or {}).get("line", 1)), what))
    return out
