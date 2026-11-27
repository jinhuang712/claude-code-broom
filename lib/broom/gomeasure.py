"""What broom reads from Go source itself: how long a function is and how long a type is with its methods, both in
code lines (decision 039), and for the smells golangci-lint has no linter for, a `recover()` whose value is dropped,
a testify assertion that any error passes, a test that asserts nothing, a print and a package variable that a function assigns (decision 042).

Each is read from the syntax tree by ast-grep's rules `go-function-lines.yml`, `go-type-lines.yml`,
`go-broad-catch.yml`, `go-broad-test-asserts.yml`, `go-debug-output.yml`, `go-globals.yml` and `go-package.yml` under
`defaults/sg/rules/` (decision 038). A string or a comment that looks like code is never taken for it, and a type
declared inside a `type ( ... )` group counts like any other. A region the grammar can't read (`unparsed.yml`) is
left out, with a note.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .reading import TOOL_TIMEOUT, Limits, Reader
from .setters import camel_setter
from .smell import nothing_key
from .syntax import Match, Rules, Span, by_file, matches, parsed
from .testrot import TEST_FILE

TYPE_LINES = "type_lines"
FUNCTION_LINES = "function_lines"
EMPTY_TEST = "go-empty-test"  # a test that asserts nothing
# The smells, the package clause, and what the grammar can't read.
GO_RULES = Rules(only="^go-(type|method|func|broad-.*|empty-test|print|fmt-print|package|unparsed)$")
STATE_RULES = Rules(only="^go-(state-.*|package|unparsed)$")  # what a package declares and its functions assign
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


def packages(found: List[Match]) -> Dict[str, str]:
    """The package each file among the matches `found` belongs to, by its package clause."""
    return {m.file: m.caught.get("NAME", "") for m in found if m.rule == "go-package"}


def counted_print(m: Match, package: Dict[str, str]) -> bool:
    """Whether the print `m` is a debug print: a builtin anywhere, and a fmt print in a test file or in a package
    other than `main`, where printing is no program's output."""
    return m.rule == "go-print" or m.file.endswith("_test.go") or package.get(m.file) != "main"


def go_text(r: Reader, rels: List[str], lim: Limits) -> Dict[str, List[Span]]:
    """Add the rows read from the trees of the Go files `rels`: a function and a type past its length limit, a
    dropped `recover()`, a debug print and, in a test file, an assertion that any error passes or a test that
    asserts nothing. Give the lines each setter takes, per file, whose boolean parameters are no flag. Without
    ast-grep, a note and none of these rows; what lies in a region the grammar can't read is left out, with a note."""
    per_file = parsed(by_file(matches(r.root, rels, r.notes, TOOL_TIMEOUT, GO_RULES), rels), r.notes)
    found = [m for ms in per_file.values() for m in ms]
    package = packages(found)
    for (rel, name), (line, size) in type_sizes(found, r.count).items():
        r.add(rel, line, TYPE_LINES, size if size > lim[TYPE_LINES][0] else None, name)
    setters: Dict[str, List[Span]] = {}
    for m in found:
        if m.smell == FUNCTION_LINES:
            r.add_length(m.file, (m.line, m.end), FUNCTION_LINES, lim[FUNCTION_LINES][0], m.caught.get("NAME"))
            if camel_setter(m.caught.get("NAME", "")):
                setters.setdefault(m.file, []).append((m.line, m.end))
        elif (m.smell == "broad_catch" or (m.smell == "broad_test_asserts" and TEST_FILE.search(m.file))
              or (m.smell == "debug_output" and counted_print(m, package))):
            name = nothing_key(m.caught.get("NAME", "")) if m.rule == EMPTY_TEST else None
            r.add(m.file, m.line, m.smell, 1, name)
    return setters


def package_files(root: Path, rels: List[str]) -> List[str]:
    """Every Go file in the folders of the Go files `rels`, relative to `root`: a package's files share its folder."""
    folders = sorted({Path(rel).parent for rel in rels if rel.endswith(".go")})
    return sorted({(folder / f.name).as_posix() for folder in folders for f in (root / folder).glob("*.go")})


def declared(per_file: Dict[str, List[Match]]) -> Dict[Tuple[str, str], Set[str]]:
    """The package variables per (folder, package), from the matches of every file of it. `_` is no variable."""
    package = packages([m for ms in per_file.values() for m in ms])
    out: Dict[Tuple[str, str], Set[str]] = {}
    for rel, ms in per_file.items():
        names = out.setdefault((str(Path(rel).parent), package.get(rel, "")), set())
        names.update(m.caught.get("NAME", "") for m in ms if m.rule == "go-state-var")
    for names in out.values():
        names.discard("_")
    return out


def unit_of(m: Match, units: List[Match]) -> Optional[int]:
    """The index among `units` of the outermost function that holds `m`; None outside every function."""
    return next((i for i, u in enumerate(units) if u.start <= m.start < u.stop), None)


def import_name(m: Match) -> str:
    """The name a file's import `m` gives its package: the name it imports it under, or else the one goimports assumes
    from its path, the last part (the one before a major version such as `v2`) without a leading `go-` and cut where a
    character no identifier holds starts, as in `yaml.v3`. `_` and `.` give none."""
    if m.rule == "go-state-import-as":
        name = m.caught.get("NAME", "")
        return "" if name in ("_", ".") else name
    parts = m.caught.get("PATH", "").strip('"`').split("/")
    if len(parts) > 1 and parts[-1][:1] == "v" and parts[-1][1:].isdigit():
        parts.pop()
    base = parts[-1].removeprefix("go-")
    return base[:next((i for i, c in enumerate(base) if not (c.isalnum() or c == "_")), len(base))]


def assigned_name(m: Match, names: Set[str], imported: Set[str]) -> str:
    """The variable the assignment `m` assigns, as `Var` for one of its package's `names` or `pkg.Var` for one of a
    package the file imports under a name among `imported`; empty for any other name or field."""
    name, pkg = m.caught.get("NAME", ""), m.caught.get("PKG")
    if pkg is None:
        return name if name in names else ""
    return f"{pkg}.{name}" if pkg in imported else ""


def first_assignments(ms: List[Match], names: Set[str]) -> List[Tuple[int, str]]:
    """The (line, variable) of one file's matches `ms` where a function first assigns one of the package variables
    `names`, or a variable of a package the file imports. `init` sets the package up, so what it assigns doesn't
    count, and `main` sets the program up, so what it assigns of another package, as `flag.Usage = usage`, doesn't
    either; neither does a name the function declares, which hides a package variable or an imported package."""
    units = [m for m in ms if m.rule == "go-state-func"]
    local = {(unit_of(m, units), m.caught.get("NAME")) for m in ms if m.rule == "go-state-local"}
    imported = {import_name(m) for m in ms if m.smell == "imported"} - {""}
    seen: Set[Tuple[Optional[int], str]] = set()
    out = []
    for m in sorted((m for m in ms if m.smell == "assigned"), key=lambda m: m.start):
        unit, name = unit_of(m, units), assigned_name(m, names, imported)
        if unit is None or not name or (unit, name.split(".")[0]) in local or (unit, name) in seen:
            continue
        seen.add((unit, name))
        setup = ("init", "main") if "." in name else ("init",)
        if units[unit].caught.get("NAME") not in setup:
            out.append((m.line, name))
    return out


def assigned_globals(root: Path, rels: List[str], notes: List[str], timeout: float) -> List[Tuple[str, int, str]]:
    """Each (file, line, variable) among the Go files `rels` where a function first assigns a variable its package
    declares, or one of a package the file imports (`pkg.Var`). The package's other files in the folder are read too,
    for the variables they declare, and only a region of `rels` the grammar can't read gets a note."""
    files, wanted = package_files(root, rels), set(rels)
    per_file = by_file(matches(root, files, notes, timeout, STATE_RULES), files)
    mine = parsed({rel: ms for rel, ms in per_file.items() if rel in wanted}, notes)
    per_file = {**parsed({rel: ms for rel, ms in per_file.items() if rel not in mine}, []), **mine}
    package = packages([m for ms in per_file.values() for m in ms])
    names = declared(per_file)
    return [(rel, line, name) for rel, ms in mine.items()
            for line, name in first_assignments(ms, names.get((str(Path(rel).parent), package.get(rel, "")), set()))]
