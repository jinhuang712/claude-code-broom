"""Old smells in the code a change touches (decision 028). A sized smell that is past its soft limit, was already past
it at the base and that the change didn't make worse is a hint when the change touches its own unit, so whoever is in
the code cleans it. A smell in a function or file the change left alone never comes up.

A unit is touched when a changed line lies in it:

- a function or a type, from its first line through its length, in every language;
- a file, when it gained lines besides imports (the caller leaves out the file length of one that didn't);
- in Python, where `ast` gives the function's range, a function with too many parameters, nesting or complexity, and
  a nested ternary in one. The other languages' tools give no range for these, so they stay as they were.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .gitutil import ChangedLines
from .reading import Limits, Raw
from .smell import Smell, level, made_worse
from .toolchain import PY_EXTS

SPANNED = ("function_lines", "type_lines")  # the row's line starts the unit and its value is the unit's length
FILE = "file_lines"
IN_FUNCTION = ("complexity", "params", "nesting", "nested_ternary")  # Python's: the function around the row's line


@lru_cache(maxsize=8)
def python_spans(text: str) -> Tuple[Tuple[int, int], ...]:
    """The first and last line of each function in Python source; none when it doesn't parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return ()
    return tuple((n.lineno, n.end_lineno or n.lineno) for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))


def span_around(text: str, line: int) -> Optional[Tuple[int, int]]:
    """The first and last line of the innermost function of Python source that holds `line`, None outside any."""
    inside = [s for s in python_spans(text) if s[0] <= line <= s[1]]
    return max(inside) if inside else None


def telling(r: Raw) -> bool:
    """Whether a touch can be told for the row: a length in any language, and in Python the rest."""
    if r.metric in SPANNED or r.metric == FILE:
        return True
    return r.metric in IN_FUNCTION and Path(r.rel).suffix in PY_EXTS


def old_smells(rows: List[Raw], before: Optional[List[Raw]], limits_of: Callable[[str], Limits],
               repo: Path) -> List[Smell]:
    """The smells in `rows` that were already past their soft limit in `before` and that the change didn't make worse,
    as hints: the ones `compare` leaves out. None for `before` is no base, so none."""
    was = {(r.rel, r.metric, r.key): r.value for r in before or []}
    out = []
    for r in rows:
        pair = limits_of(r.rel).get(r.metric)
        old = was.get((r.rel, r.metric, r.key))
        if pair and telling(r) and old is not None and level(r.value, pair) and not made_worse(r.value, old, pair):
            out.append(Smell(repo, repo / r.rel, r.line, r.metric, r.key, r.value, old, r.tool, "hint", pair[0],
                             touched=True))
    return out


def touches(s: Smell, lines: Optional[Set[int]], text: str) -> bool:
    """Whether a changed line (`lines`, None for every line) lies in the unit of `s`; `text` is the file's source."""
    if s.metric == FILE or lines is None:
        return True
    span = (s.line, s.line + s.value - 1) if s.metric in SPANNED else span_around(text, s.line)
    return span is not None and not lines.isdisjoint(range(span[0], span[1] + 1))


def touched(old: List[Smell], base: str, texts: Dict[str, str]) -> List[Smell]:
    """Those of the `old` smells whose unit the files' changes since `base` touch. `texts` holds each file's current
    source by path, which Python's functions are found in."""
    if not old:
        return []
    changed = ChangedLines(base)
    return [s for s in old if touches(s, changed.get(s.file), texts.get(str(s.file.relative_to(s.repo)), ""))]
