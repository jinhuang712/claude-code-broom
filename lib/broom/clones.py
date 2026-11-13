"""Duplicate code, found by jscpd 5. It scans every code file in the repo, so new code that repeats old code
anywhere is found; with a base revision it also scans that tree and marks the clones the base didn't have."""

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


def find_clones(repo: Path, base: Optional[str], min_lines: int, skip_dirs: List[str],
                notes: List[str]) -> List[Clone]:
    exe = shutil.which("jscpd")
    if not exe:
        notes.append("missing:jscpd (npm i -g jscpd), so duplicate code isn't measured")
        return []
    with tempfile.TemporaryDirectory(prefix="broom-jscpd-") as out:
        cmd = [exe, "-f", FORMATS, "--min-lines", str(min_lines), "-r", "json", "-o", out, "--no-tips", "-s",
               "-i", ",".join(f"**/{d}/**" for d in skip_dirs), "."]
        if base:
            cmd[1:1] = ["--baseline-from-ref", base]
        rc, _, err = run(cmd, repo, timeout=TIMEOUT)
        if rc is None:
            notes.append("timeout:jscpd measuring duplicate code")
            return []
        try:
            found = json.loads((Path(out) / "jscpd-report.json").read_text()).get("duplicates", [])
        except (OSError, ValueError):
            notes.append(f"jscpd failed (version 5 or later needed): {err.strip()[:120]}")
            return []
    return [Clone(d["firstFile"]["name"], int(d["firstFile"]["start"]), d["secondFile"]["name"],
                  int(d["secondFile"]["start"]), int(d["lines"]), bool(d.get("isNew"))) for d in found]
