"""What broom reads from Go source itself: how long a function is and how long a type is with its methods, both in
code lines (decision 039), and for the smells golangci-lint has no linter for, a `recover()` whose value is dropped
and a testify assertion that any error passes.

Each is read from the syntax tree by ast-grep's rules `go-function-lines.yml`, `go-type-lines.yml`,
`go-broad-catch.yml` and `go-broad-test-asserts.yml` under `defaults/sg/rules/` (decision 038), in one run over the
files. A string or a comment
that looks like code is never taken for it, and a type declared inside a `type ( ... )` group counts like any other. A
region the grammar can't read (`unparsed.yml`) is left out, with a note.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from .reading import TOOL_TIMEOUT, Limits, Reader
from .syntax import Match, Rules, by_file, matches, parsed

TYPE_LINES = "type_lines"
FUNCTION_LINES = "function_lines"
GO_RULES = Rules(only="^go-(type|method|func|broad-.*|unparsed)$")  # the smells, and what the grammar can't read
Count = Callable[[str, int, int], int]  # the code lines of a file from one line through another


def type_sizes(found: List[Match], count: Optional[Count] = None) -> Dict[Tuple[str, str], List[int]]:
    """Per (file, type) among the matches `found`, the line the type is first seen on and its code lines there, as
    `count` gives them (every line without it): its struct or interface declaration plus every method on it. Methods
    in the package's other files aren't added."""
    sizes: Dict[Tuple[str, str], List[int]] = {}
    for m in sorted(found, key=lambda m: (m.file, m.line)):
        if m.smell == TYPE_LINES:
            lines = count(m.file, m.line, m.end) if count else m.lines
            sizes.setdefault((m.file, m.caught.get("NAME", "")), [m.line, 0])[1] += lines
    return sizes


def go_text(r: Reader, rels: List[str], lim: Limits) -> None:
    """Add the rows read from the trees of the Go files `rels`: a function and a type past its length limit, a
    dropped `recover()` and, in a test file, an assertion that any error passes. Without ast-grep, a note and none of
    these rows; what lies in a region the grammar can't read is left out, with a note."""
    per_file = parsed(by_file(matches(r.root, rels, r.notes, TOOL_TIMEOUT, GO_RULES), rels), r.notes)
    found = [m for ms in per_file.values() for m in ms]
    for (rel, name), (line, size) in type_sizes(found, r.count).items():
        r.add(rel, line, TYPE_LINES, size if size > lim[TYPE_LINES][0] else None, name)
    for m in found:
        if m.smell == FUNCTION_LINES:
            r.add_length(m.file, (m.line, m.end), FUNCTION_LINES, lim[FUNCTION_LINES][0], m.caught.get("NAME"))
        elif m.smell == "broad_catch" or (m.smell == "broad_test_asserts" and m.file.endswith("_test.go")):
            r.add(m.file, m.line, m.smell, 1)
