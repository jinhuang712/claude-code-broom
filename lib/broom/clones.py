"""Duplicate and dead code, found by jscpd 5. Both need the whole repo: new code that repeats old code anywhere,
or code nothing anywhere uses. For duplicates, a base revision makes jscpd scan that tree too and mark the
clones the base didn't have; dead code (JavaScript, TypeScript and Python) leaves out tests and entry points."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .common import run

FORMATS = "javascript,typescript,jsx,tsx,python,go,swift"
TIMEOUT = 120


@dataclass
class Clone:
    rel: str
    line: int
    other: str
    other_line: int
    lines: int
    new: bool  # absent at the base revision


@dataclass
class Unused:
    rel: str
    line: int
    what: str  # "export `name`", "symbol `name`", "import `name`", "this file", ...


def run_jscpd(repo: Path, args: List[str], report: str, skip_dirs: List[str], notes: List[str]) -> Optional[dict]:
    """jscpd's JSON report for `args` over the repo, or None with a note when it is missing or fails."""
    exe = shutil.which("jscpd")
    if not exe:
        notes.append("missing:jscpd (npm i -g jscpd), so duplicate and dead code aren't measured")
        return None
    with tempfile.TemporaryDirectory(prefix="broom-jscpd-") as out:
        cmd = [exe, *args, "-r", "json", "-o", out, "--no-tips", "-s",
               "-i", ",".join(f"**/{d}/**" for d in skip_dirs), "."]
        rc, _, err = run(cmd, repo, timeout=TIMEOUT)
        if rc is None:
            notes.append("timeout:jscpd")
            return None
        try:
            return json.loads((Path(out) / report).read_text())
        except (OSError, ValueError):
            notes.append(f"jscpd failed (version 5 or later needed): {err.strip()[:120]}")
            return None


def find_clones(repo: Path, base: Optional[str], min_lines: int, skip_dirs: List[str],
                notes: List[str]) -> List[Clone]:
    args = ["-f", FORMATS, "--min-lines", str(min_lines), *(["--baseline-from-ref", base] if base else [])]
    found = (run_jscpd(repo, args, "jscpd-report.json", skip_dirs, notes) or {}).get("duplicates", [])
    return [Clone(d["firstFile"]["name"], int(d["firstFile"]["start"]), d["secondFile"]["name"],
                  int(d["secondFile"]["start"]), int(d["lines"]), bool(d.get("isNew"))) for d in found]


def find_unused(repo: Path, skip_dirs: List[str], notes: List[str]) -> List[Unused]:
    found = (run_jscpd(repo, ["--dead-code"], "basta-report.json", skip_dirs, notes) or {}).get("findings", [])
    out = []
    for f in found:
        kind = str(f.get("category", "")).replace("unused-", "")
        what = "this file" if kind == "file" else f"{kind} `{f.get('name', '')}`"
        out.append(Unused(f.get("path", ""), int((f.get("start") or {}).get("line", 1)), what))
    return out
