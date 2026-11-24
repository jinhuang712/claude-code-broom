"""A change against its base: the lines it changed in each file, which of them it only moved, and which of them are
code lines. The checks that have no copy of the base to compare with (smells.real_tree_smells) ask it what makes a
finding the change's own."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Dict, Optional, Set

from .codelines import CodeLines
from .gitutil import ChangedLines
from .touched import changed_code


def moved_lines(lines: Set[int], now: str, before: str) -> Set[int]:
    """The changed `lines` of a file whose text, trimmed, it already had at the base: lines a change only moved,
    such as an import that a sort or a removal above it put elsewhere. A text counts as moved as many times as the
    base held it beyond the unchanged lines that still hold it."""
    left = Counter(row.strip() for row in before.splitlines())
    rows = now.splitlines()
    left.subtract(row.strip() for n, row in enumerate(rows, 1) if n not in lines)
    out: Set[int] = set()
    for n in sorted(lines):
        text = rows[n - 1].strip() if 0 < n <= len(rows) else ""
        if text and left[text] > 0:
            left[text] -= 1
            out.add(n)
    return out


class Change:
    """A change against its `base` (None for a sweep of everything): the lines it changed in each file, and which of
    them it only moved, read from the files `now` and as they were `before`. `code` gives the code lines of the files
    as they are, read here when the caller has none."""

    def __init__(self, repo: Path, base: Optional[str], now: Optional[Dict[str, str]] = None,
                 before: Optional[Dict[str, str]] = None, code: Optional[CodeLines] = None) -> None:
        self.repo = repo
        self.changed = ChangedLines(base) if base else None
        self.now = now or {}
        self.before = before or {}
        self.code = code or CodeLines(self.now, [])
        self._moved: Dict[str, Set[int]] = {}

    def lines(self, rel: str) -> Optional[Set[int]]:
        """The changed lines of `rel`; None when every line counts."""
        return self.changed.get(self.repo / rel) if self.changed else None

    def code_lines(self, rel: str) -> Optional[Set[int]]:
        """The changed lines of `rel` that are code lines: a comment or a blank line a change adds touches nothing."""
        return changed_code(self.lines(rel), self.code.of([rel]).get(rel))

    def only_moved(self, rel: str, line: int) -> bool:
        """Whether `line` of `rel` is a changed line whose text the file already held at the base."""
        lines = self.lines(rel)
        if lines is None or rel not in self.now or rel not in self.before:
            return False
        if rel not in self._moved:
            self._moved[rel] = moved_lines(lines, self.now[rel], self.before[rel])
        return line in self._moved[rel]
