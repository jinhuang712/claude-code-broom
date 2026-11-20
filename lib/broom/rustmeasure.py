"""What broom reads from Rust source itself, for the smells clippy has no lint for: magic numbers, commented-out code,
global state, how long a type is with its impls, tests that any error passes, handlers that catch every error and an
`if` expression nested in another's branch.

Each is read from the syntax tree by ast-grep (decision 038), with the rules in `defaults/sg/rules/rust-*.yml`; this
file only joins what they match. A region the grammar can't read is left out, with a note. Test code is a file under
`tests/` or named as a test, or an item under `#[cfg(test)]` or marked as a test.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .reading import TOOL_TIMEOUT, Limits, Reader
from .state import DEFAULTS
from .syntax import Match, matches

TYPE_LINES = "type_lines"
PROBE = DEFAULTS / "sg" / "probe" / "sgconfig.yml"
# A file of tests by its path: what lies under `tests/`, `tests.rs`, `*_test.rs` and `*_tests.rs`.
TEST_PATH = re.compile(r"(^|/)tests(/|\.rs$)|_tests?\.rs$")
TEST_ITEM = "rust-test-item"
UNPARSED = "rust-unparsed"
# Smells a rule's match is on its own, anywhere; and those that count outside test code, or only inside it.
WHOLE = {"globals", "broad_catch", "nested_ternary"}
OUTSIDE_TESTS = {"magic_numbers"}
INSIDE_TESTS = {"broad_test_asserts"}
PLAIN = {0, 1, 2}
# A number token: a based integer, or a decimal one, each with the suffix of its type.
LITERAL = re.compile(r"(?:(?P<int>0[xX][\da-fA-F]+|0[oO][0-7]+|0[bB][01]+)(?:[iu](?:8|16|32|64|128|size))?"
                     r"|(?P<float>[\d.]+(?:[eE][+-]?\d+)?)(?:[iu](?:8|16|32|64|128|size)|f32|f64)?)")
EVERY_LINE = (1, 1 << 30)
PROBE_HEAD = 2  # the line of a probe file that holds the comment's first line: it follows `fn broom_probe() {`
PROBE_LINES = 3  # the lines one comment takes when each has a probe function of its own
Span = Tuple[int, int]
BATCH = 2000  # files per run of ast-grep: a command line holds only so many paths


def rust_tree(root: Path, rels: List[str], notes: List[str]) -> Dict[str, List[Match]]:
    """The matches of broom's rules in the Rust files `rels` under `root`, per file. What lies in a region the grammar
    can't read is left out, with a note for the file."""
    found: Dict[str, List[Match]] = {rel: [] for rel in rels}
    for start in range(0, len(rels), BATCH):
        for m in matches(root, rels[start:start + BATCH], notes, TOOL_TIMEOUT):
            found.setdefault(m.file, []).append(m)
    for rel, ms in found.items():
        broken = spans(ms, UNPARSED)
        if broken:
            notes.append(f"ast-grep can't parse {rel} from line {broken[0][0]}: smells there go unmeasured")
            found[rel] = [m for m in ms if m.rule != UNPARSED and not inside(m.line, broken)]
    return found


def spans(found: List[Match], rule: str) -> List[Span]:
    """The first and last line of each match of `rule`."""
    return [(m.line, m.end) for m in found if m.rule == rule]


def inside(line: int, among: List[Span]) -> bool:
    """Whether `line` lies in one of the spans."""
    return any(first <= line <= last for first, last in among)


def test_spans(rel: str, found: List[Match]) -> List[Span]:
    """The lines of test code in the file `rel`: all of a test file, else each item under `#[cfg(test)]` or marked
    as a test."""
    return [EVERY_LINE] if TEST_PATH.search(rel) else spans(found, TEST_ITEM)


def plain(literal: str) -> bool:
    """Whether a number literal (one token the tree isolated) is 0, 1 or 2, which count things and need no name."""
    m = LITERAL.fullmatch(literal.replace("_", ""))
    if not m:
        return True
    value = int(m["int"], 0) if m["int"] else float(m["float"])
    return value in PLAIN


# ---------------------------------------------------------------- types with their impls


def type_sizes(found: List[Match]) -> Dict[str, List[int]]:
    """Per type declared or implemented in the file, the line it is first seen on and its lines there: its item plus
    every impl of it. impls in other files aren't added."""
    sizes: Dict[str, List[int]] = {}
    for m in sorted(found, key=lambda m: m.line):
        name = m.caught.get("NAME")
        if m.smell == TYPE_LINES and name:
            sizes.setdefault(name, [m.line, 0])[1] += m.lines
    return sizes


# ---------------------------------------------------------------- commented-out code

Comment = Tuple[str, int, str]  # the file, the line and the text after `//` of a comment


def own_lines(root: Path, rel: str, found: List[Match]) -> List[Match]:
    """The comments among `found` that start their line in the file `rel`: one after code on its line is a note on
    that code."""
    try:
        rows = (root / rel).read_text(errors="replace").splitlines()
    except OSError:
        return []
    return [m for m in found if m.smell == "commented_code" and m.line <= len(rows)
            and rows[m.line - 1].lstrip().startswith(m.caught.get("C", "//"))]


def comment_runs(root: Path, found: Dict[str, List[Match]]) -> List[List[Comment]]:
    """The `//` comments of each file that aren't doc comments and start their line, in runs of comments on lines
    one after another."""
    runs: List[List[Comment]] = []
    for rel, ms in found.items():
        last = -1
        for m in sorted(own_lines(root, rel, ms), key=lambda m: m.line):
            comment = (rel, m.line, m.caught.get("C", "")[2:])
            if m.line == last + 1:
                runs[-1].append(comment)
            else:
                runs.append([comment])
            last = m.line
    return runs


def as_one_body(lines: List[str]) -> str:
    """A probe file that holds comment texts `lines` as the body of one function."""
    return "fn broom_probe() {\n" + "\n".join(lines) + "\n}\n"


def one_body_each(lines: List[str]) -> str:
    """A probe file that holds each of the comment texts `lines` as the body of a function of its own, which takes
    `PROBE_LINES` lines."""
    return "".join(f"fn broom_probe() {{\n{line}\n}}\n" for line in lines)


def probe(sources: List[str], notes: List[str]) -> List[Tuple[List[Span], bool]]:
    """Per probe file of `sources`, the lines (1-based) of each statement, item or expression of more than one word
    that ast-grep reads as a probe function's body and that no unreadable region touches; and whether the file holds
    such a region at all."""
    with tempfile.TemporaryDirectory() as tmp:
        names = [f"c{n}.rs" for n in range(len(sources))]
        for name, source in zip(names, sources):
            (Path(tmp) / name).write_text(source)
        found = matches(Path(tmp), names, notes, TOOL_TIMEOUT, PROBE) if names else []
    code: Dict[str, List[Span]] = {name: [] for name in names}
    broken: Dict[str, List[Span]] = {name: [] for name in names}
    for m in found:
        (code if m.rule == "rust-probe-code" else broken)[m.file].append((m.line, m.end))
    return [([(first, last) for first, last in code[name] if not any(a <= last and first <= b for a, b in broken[name])],
             bool(broken[name])) for name in names]


def commented_code(root: Path, found: Dict[str, List[Match]], notes: List[str]) -> Iterator[Tuple[str, int]]:
    """The file and line of each comment where code starts: read with the comments around it as one body, and where
    prose around it breaks that, each comment alone."""
    runs = comment_runs(root, found)
    whole = probe([as_one_body([c[2] for c in run]) for run in runs], notes)
    starts = [{first - PROBE_HEAD for first, _ in spans} for spans, _ in whole]
    broken = [n for n, (_, bad) in enumerate(whole) if bad and len(runs[n]) > 1]
    alone = probe([one_body_each([c[2] for c in runs[n]]) for n in broken], notes)
    for n, (spans, _) in zip(broken, alone):
        covered = [(a - PROBE_HEAD, b - PROBE_HEAD) for a, b in whole[n][0]]
        found_alone = {(a - PROBE_HEAD) // PROBE_LINES for a, _ in spans if (a - PROBE_HEAD) % PROBE_LINES == 0}
        starts[n] |= {k for k in found_alone if not inside(k, covered)}
    for run, indexes in zip(runs, starts):
        yield from (run[n][:2] for n in sorted(indexes))


# ---------------------------------------------------------------- the rows


def file_rows(r: Reader, rel: str, found: List[Match], lim: Limits) -> None:
    """Add the rows of one file's matches: its long types, and each smell a match is where it stands."""
    for name, (line, size) in type_sizes(found).items():
        r.add(rel, line, TYPE_LINES, size if size > lim[TYPE_LINES][0] else None, name)
    tests = test_spans(rel, found)
    for m in found:
        if m.smell in WHOLE or m.smell in INSIDE_TESTS and inside(m.line, tests):
            r.add(rel, m.line, m.smell, 1)
        elif m.smell in OUTSIDE_TESTS and not inside(m.line, tests) and not plain(m.caught.get("N", "0")):
            r.add(rel, m.line, m.smell, 1)


def rust_text(r: Reader, rels: List[str], lim: Limits) -> None:
    """Add the rows read from the syntax trees of the Rust files `rels`."""
    found = rust_tree(r.root, rels, r.notes)
    for rel, ms in found.items():
        file_rows(r, rel, ms, lim)
    for rel, line in commented_code(r.root, found, r.notes):
        r.add(rel, line, "commented_code", 1)


def files_with_tests(root: Path, rels: List[str]) -> Optional[Set[str]]:
    """Those of the Rust files `rels` under `root` that hold a test or a `#[cfg(test)]` item; None when the tree
    can't be read (no ast-grep), so that no file is taken for untested."""
    notes: List[str] = []
    found = rust_tree(root, rels, notes)
    if any(n.startswith(("missing:", "timeout:", "failed:")) for n in notes):
        return None
    return {rel for rel, ms in found.items() if spans(ms, TEST_ITEM)}
