"""What every language's smell measurer shares: a row per finding, and a reader that collects them."""

from __future__ import annotations

import json
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

Limits = Dict[str, Tuple[int, int]]
TOOL_TIMEOUT = 90


@dataclass
class Raw:
    """One measurement from a tool: its file (`rel`), line, metric, value, and the key matching it across versions.
    A length is in code lines (decision 039), so `span` keeps how many lines of the file its function or type takes
    from `line` on, where the tool says; 0 where it doesn't."""
    rel: str
    line: int
    metric: str
    key: str  # what matches a finding across versions: the function's name, else the line's text
    value: int
    tool: str
    span: int = 0


class Reader:
    """Turns one tool's findings in one scratch tree into Raw rows."""

    def __init__(self, root: Path, tool: str, notes: List[str]) -> None:
        self.root, self.tool, self.notes = root, tool, notes
        self.rows: List[Raw] = []
        self.code: Dict[str, List[int]] = {}  # per file of the scratch tree, its code lines in order (codelines)

    def count(self, rel: str, first: int, last: int) -> int:
        """How many code lines the file `rel` holds from line `first` through `last`: what a length is. Every line of
        them for a file whose code lines weren't read."""
        return lines_in(self.code.get(self.rel(rel)), first, last)

    def add_length(self, rel: str, span: Tuple[int, int], metric: str, soft: int, name: Optional[str] = None) -> None:
        """Record the length of the function or type that takes the lines `span` (a first and a last) of `rel`, in
        code lines; nothing when that isn't past `soft`."""
        first, last = span
        size = self.count(rel, first, last)
        if size > soft:
            self.add(rel, first, metric, size, name)
            self.rows[-1].span = last - first + 1

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

    def add(self, rel: str, line: int, metric: str, value: Optional[int], name: Optional[str] = None) -> Optional[Raw]:
        """Record one measurement as a Raw row, skipping a None value (none is given then); `name` overrides the key
        from the line."""
        if value is None:
            return None
        rel = self.rel(rel)
        text = self.line_text(rel, line)
        key = name or match(r"\b(?:def|func|function|fn)\s+([A-Za-z_]\w*)", text) or text
        self.rows.append(Raw(rel, line, metric, key, value, self.tool))
        return self.rows[-1]

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


def lines_in(code: Optional[List[int]], first: int, last: int) -> int:
    """How many of the code lines `code` (sorted) lie from `first` through `last`; every line of that range when the
    file's code lines are unknown (None)."""
    if code is None:
        return last - first + 1
    return bisect_right(code, last) - bisect_left(code, first)


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
