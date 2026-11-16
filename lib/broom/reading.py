"""What every language's smell measurer shares: a row per finding, and a reader that collects them."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

Limits = Dict[str, Tuple[int, int]]
TOOL_TIMEOUT = 90


@dataclass
class Raw:
    """One measurement from a tool: its file (`rel`), line, metric, value, and the key matching it across versions."""
    rel: str
    line: int
    metric: str
    key: str  # what matches a finding across versions: the function's name, else the line's text
    value: int
    tool: str


class Reader:
    """Turns one tool's findings in one scratch tree into Raw rows."""

    def __init__(self, root: Path, tool: str, notes: List[str]) -> None:
        self.root, self.tool, self.notes = root, tool, notes
        self.rows: List[Raw] = []

    def json(self, rc: Optional[int], out: str, empty):
        """Parse a tool's JSON `out`; a timeout, or empty or bad output, adds a note and gives `empty`."""
        if rc is None:
            self.notes.append(f"timeout:{self.tool} measuring smells")
            return empty
        try:
            return json.loads(out) if out.strip() else empty
        except ValueError:
            self.notes.append(f"{self.tool} failed measuring smells: {out.strip()[:120]}")
            return empty

    def add(self, rel: str, line: int, metric: str, value: Optional[int], name: Optional[str] = None) -> None:
        """Record one measurement as a Raw row, skipping a None value; `name` overrides the key from the line."""
        if value is None:
            return
        rel = self.rel(rel)
        text = self.line_text(rel, line)
        key = name or match(r"\b(?:def|func|function|fn)\s+([A-Za-z_]\w*)", text) or text
        self.rows.append(Raw(rel, line, metric, key, value, self.tool))

    def rel(self, name: str) -> str:
        """`name` relative to the scratch tree's root when it lies under the root, else unchanged."""
        p = Path(name)
        if not p.is_absolute():
            return name
        try:
            return str(p.resolve().relative_to(self.root.resolve()))
        except ValueError:
            return name

    def line_text(self, rel: str, line: int) -> str:
        """The stripped text of line `line` (1-based) of file `rel` under the root; "" when it can't be read."""
        try:
            rows = (self.root / rel).read_text(errors="replace").splitlines()
        except OSError:
            return ""
        return rows[line - 1].strip() if 0 < line <= len(rows) else ""


def number(pattern: str, text: str) -> Optional[int]:
    """The first group of `pattern` in `text` as an int; None when there is no match."""
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def match(pattern: str, text: str) -> Optional[str]:
    """The first group of `pattern` in `text`; None when there is no match."""
    m = re.search(pattern, text)
    return m.group(1) if m else None


def quoted_name(text: str) -> Optional[str]:
    """The name in the first backtick or quoted span of `text`; None when there is none."""
    return match(r"[`']([^`']+)[`']", text)
