"""What broom reads from Go source itself, for the smells golangci-lint has no linter for: how long a type is with its
methods, a `recover()` whose value is dropped, and a testify assertion that any error passes.

gofmt's layout is what makes the text enough: a declaration starts at the first column, and the brace that closes it
stands at the first column too. A raw string that holds such a brace ends a block early, so its type reads shorter.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .reading import Limits, Reader

TYPE_LINES = "type_lines"
# `type Name struct {` or `type Name interface {`, generic or not; one inside a `type ( ... )` group is not read.
TYPE_START = re.compile(r"^type (\w+)(?:\[[^\]]*\])? (?:struct|interface) \{\s*$")
# `func (r *Name) Method(` and `func (Name[T]) Method(`: the type a method is on.
METHOD = re.compile(r"^func \((?:\w+ )?\*?(\w+)(?:\[[^\]]*\])?\) \w")
# `recover()` as a statement of its own or assigned to `_`: every panic is caught and none is looked at.
DROPPED_RECOVER = re.compile(r"(?:^|[{;])\s*(?:_\s*=\s*)?recover\(\)\s*(?:$|[;}])")
# testify's assertions that any error or any panic passes; `ErrorIs`, `ErrorAs`, `ErrorContains`, `EqualError` and
# `PanicsWithValue` say which. `s.Error(` is left out: on a `*testing.T` that name reports a failure.
ANY_ERROR = re.compile(r"\b(?:assert|require)\.(?:Error|Panics)f?\(|\.(?:Assert|Require)\(\)\.(?:Error|Panics)f?\(")
COMMENT = re.compile(r"\s*//.*$")


def block_end(rows: List[str], start: int) -> int:
    """The index of the row that closes the declaration opened on row `start`: that row itself for a one-line
    method, else the next row with a brace at its first column."""
    if rows[start].rstrip().endswith("}"):
        return start
    return next((n for n in range(start + 1, len(rows)) if rows[n].startswith("}")), len(rows) - 1)


def type_sizes(rows: List[str]) -> Dict[str, List[int]]:
    """Per type named in the file, the line it is first seen on and its lines there: its struct or interface
    declaration plus every method on it. Methods in the package's other files aren't added."""
    sizes: Dict[str, List[int]] = {}
    n = 0
    while n < len(rows):
        found = TYPE_START.match(rows[n]) or METHOD.match(rows[n])
        if not found:
            n += 1
            continue
        end = block_end(rows, n)
        sizes.setdefault(found[1], [n + 1, 0])[1] += end - n + 1
        n = end + 1
    return sizes


def go_text(r: Reader, rels: List[str], lim: Limits) -> None:
    """Add the rows read from the text of the Go files `rels`: a type past its length limit, a dropped `recover()`
    and, in a test file, an assertion that any error passes."""
    for rel in rels:
        rows = (r.root / rel).read_text(errors="replace").splitlines()
        for name, (line, size) in type_sizes(rows).items():
            r.add(rel, line, TYPE_LINES, size if size > lim[TYPE_LINES][0] else None, name)
        in_test = rel.endswith("_test.go")
        for n, row in enumerate(rows, 1):
            code = COMMENT.sub("", row)
            if DROPPED_RECOVER.search(code):
                r.add(rel, n, "broad_catch", 1)
            if in_test and ANY_ERROR.search(code):
                r.add(rel, n, "broad_test_asserts", 1)
