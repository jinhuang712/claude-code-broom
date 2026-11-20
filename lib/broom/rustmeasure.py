"""What broom reads from Rust source itself, for the smells clippy has no lint for: magic numbers, commented-out code,
global state, how long a type is with its impls, tests that any error passes, and handlers that catch every error.

The text is read with its strings and comments blanked out, so a number in a string or a brace in a comment isn't
code. rustfmt's layout is what makes that enough: an item starts at the first column, and the brace that closes it
stands at the first column too. Test code is a file under `tests/` or named as a test, or what follows a
`#[cfg(test)]`, which rustfmt and custom keep at the end of the file.
"""

from __future__ import annotations

import re
from typing import Dict, Iterator, List, Set, Tuple

from .reading import Limits, Reader

TYPE_LINES = "type_lines"
# What is code to step over: a `//` comment, a `/*` comment, a raw string, a string, a char literal. A lifetime
# (`'a`) has no closing quote, so it stays code.
TOKEN = re.compile(r"""(?P<line>//[^\n]*)|(?P<block>/\*)|(?P<raw>\bb?r(?P<hashes>\#*)")|(?P<str>\bb?"|")"""
                   r"""|(?P<char>\bb?'(?:\\[^\n]+?|[^\\'\n])'|'(?:\\[^\n]+?|[^\\'\n])')""")
STRING_END = re.compile(r'(?:\\.|[^"\\])*"', re.S)
BLOCK_MARK = re.compile(r"/\*|\*/")
Comment = Tuple[int, str]  # the line of a comment that starts its line, and its text


def blank(text: str) -> str:
    """`text` with all but its line breaks turned into spaces."""
    return re.sub(r"[^\n]", " ", text)


def token_end(text: str, m: re.Match) -> int:
    """Where the comment, string or char literal that `m` starts ends in `text`."""
    if m["line"] or m["char"]:
        return m.end()
    if m["raw"]:
        end = text.find('"' + m["hashes"], m.end())
        return len(text) if end < 0 else end + 1 + len(m["hashes"])
    if m["str"]:
        found = STRING_END.match(text, m.end())
        return found.end() if found else len(text)
    depth, at = 1, m.end()  # a block comment: they nest
    while depth and at < len(text):
        nxt = BLOCK_MARK.search(text, at)
        if not nxt:
            return len(text)
        depth += 1 if nxt.group() == "/*" else -1
        at = nxt.end()
    return at


def clean(text: str) -> Tuple[List[str], List[Comment]]:
    """The rows of `text` with strings and comments blanked, and the `//` comments that start their line."""
    text = "\n".join(text.splitlines())  # one kind of line break, so lines count as the file's do
    out: List[str] = []
    comments: List[Comment] = []
    pos = line = 0
    while True:
        m = TOKEN.search(text, pos)
        if not m:
            break
        line += text.count("\n", pos, m.start())
        end = token_end(text, m)
        if m["line"] and not text[text.rfind("\n", 0, m.start()) + 1:m.start()].strip():
            comments.append((line + 1, m.group()))
        out += [text[pos:m.start()], blank(text[m.start():end])]
        line += text.count("\n", m.start(), end)
        pos = end
    return "".join(out + [text[pos:]]).splitlines(), comments


def test_start(rel: str, rows: List[str]) -> int:
    """The index of the first row of test code: 0 in a file under `tests/` or named `tests.rs`, `*_test.rs` or
    `*_tests.rs`, else the first `#[cfg(test)]`; past the end when there is none."""
    if re.search(r"(^|/)tests(/|\.rs$)|_tests?\.rs$", rel):
        return 0
    return next((n for n, row in enumerate(rows) if re.match(r"\s*#\[cfg\(test\)\]", row)), len(rows))


# ---------------------------------------------------------------- magic numbers

NUMBER = re.compile(r"(?:(?<![\w.])|(?<=\.\.))(0x[\da-fA-F_]+|0o[0-7_]+|0b[01_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)"
                    r"(?:_?[iuf](?:8|16|32|64|128|size))?\b")
# What stands before a number that is compared, computed with, returned or passed; or after one that is compared or
# computed with. `= 5`, `[0; 64]`, `x[3]` and `field: 8` are none of these.
# rustfmt sets a comparison's `<` and `>` apart with spaces, and a generic's `<` against its name.
BEFORE = re.compile(r"(?:==|!=|\s[<>]=?|=>|\.\.=?|<<=?|>>=?|[-+*/%&|^]=?|\breturn)\s*$")
AFTER = re.compile(r"\s*(?:==|!=|[-+*/%^]|\.\.|<<|>>)|\s+(?:[<>]|&&?|\|\|?)\s")
ARGUMENT = re.compile(r"[(,]\s*$")
OPENS = {")": "(", "]": "[", "}": "{", ">": "<"}
DECLARED = re.compile(r"\s*(?:pub(?:\([^)]*\))?\s+)?(?:const|static)\s")
ENUM = re.compile(r"\s*(?:pub(?:\([^)]*\))?\s+)?enum\s")
PLAIN = {"0", "1", "2"}


def declared_lines(rows: List[str]) -> Set[int]:
    """The indexes of rows whose numbers name themselves: attributes, const and static items to their `;`, and enums
    to their closing brace."""
    out: Set[int] = set()
    n = 0
    while n < len(rows):
        row = rows[n]
        if row.lstrip().startswith("#"):
            out.add(n)
        elif DECLARED.match(row) or ENUM.match(row):
            closer = ";" if DECLARED.match(row) else "}"
            end = next((k for k in range(n, len(rows)) if rows[k].rstrip().endswith(closer)), n)
            out.update(range(n, end + 1))
            n = end
        n += 1
    return out


def plain(literal: str) -> bool:
    """Whether a number literal is 0, 1 or 2, which count things and need no name."""
    digits = literal.replace("_", "")
    if digits[:2] in ("0x", "0o", "0b"):
        return str(int(digits, 0)) in PLAIN
    try:
        value = float(digits)
    except ValueError:
        return True
    return value in (0, 1, 2)


def innermost(head: str) -> str:
    """The bracket still open at the end of `head`, the start of a row: `(` of a call, `[` of an array, `<` of a
    generic (one that follows a name); "" when the row opens none."""
    closed: List[str] = []
    for i in range(len(head) - 1, -1, -1):
        ch = head[i]
        before = head[i - 1] if i else " "
        generic = before.isalnum() or before in ("_:" if ch == "<" else "_>)]")
        if ch in OPENS and (ch != ">" or generic):
            closed.append(OPENS[ch])
        elif ch in "([{" or ch == "<" and generic:
            if not closed:
                return ch
            closed.pop()
    return ""


def magic_lines(rows: List[str], start: int) -> Iterator[int]:
    """The 1-based lines before the test code with a number in a comparison, a computation, a return or a call."""
    skip = declared_lines(rows)
    for n, row in enumerate(rows[:start]):
        if n in skip:
            continue
        for m in NUMBER.finditer(row):
            head = row[:m.start()]
            used = BEFORE.search(head) or AFTER.match(row, m.end())
            if not plain(m[1]) and (used or ARGUMENT.search(head) and innermost(head) == "("):
                yield n + 1
                break


# ---------------------------------------------------------------- comments, globals, tests, handlers

CODE_COMMENT = re.compile(r"//(?![/!])\s*(?:(?:let|fn|use|return)\s.*|.*[;{}])\s*$")
GLOBAL = re.compile(r"\s*(?:pub(?:\([^)]*\))?\s+)?static\s+(?:mut\b|\w+\s*:[^=]*\b(?:Mutex|RwLock|RefCell|Cell|Atomic\w+"
                    r"|OnceLock|OnceCell|LazyLock|LazyCell|Lazy)\b)|.*\b(?:thread_local|lazy_static)!\s*[{(]")
ANY_ERROR = re.compile(r"#\[should_panic\s*\]|\bassert!\s*\(.*\.is_err\(\)\s*\)"
                       r"|\bassert!\s*\(\s*matches!\s*\(.*,\s*Err\s*\(\s*_\s*\)\s*\)")
ANY_ERR_ARM = re.compile(r"\bErr\s*\(\s*_\s*\)\s*=>")
# `catch_unwind(` that starts a statement, alone or assigned to `_`: every panic is caught, and none looked at.
UNWIND = re.compile(r"^\s*(?P<drop>(?:let\s+)?_\s*(?::[^=]*)?=\s*)?(?:[\w:]+::)?catch_unwind\s*\(")


def call_end(text: str, at: int) -> int:
    """The index just past the `)` that closes the `(` before index `at` in `text`."""
    depth = 1
    for i in range(at, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if not depth:
            return i + 1
    return len(text)


def dropped_unwinds(rows: List[str]) -> Iterator[int]:
    """The 1-based lines of a `catch_unwind` whose result is dropped: assigned to `_`, or a statement of its own."""
    text = "\n".join(rows)
    offsets = [0]
    for row in rows:
        offsets.append(offsets[-1] + len(row) + 1)
    for n, row in enumerate(rows):
        m = UNWIND.match(row)
        if m and (m["drop"] or re.match(r"\s*(?:\.ok\(\))?\s*;", text[call_end(text, offsets[n] + m.end()):])):
            yield n + 1


# ---------------------------------------------------------------- types with their impls

TYPE_START = re.compile(r"(?:pub(?:\([^)]*\))?\s+)?(?:unsafe\s+)?(?:struct|enum|trait|union)\s+(\w+)")


def impl_target(row: str) -> str:
    """The name of the type an `impl` row is for: `impl<T> Trait for path::Name<T> {` is for `Name`; "" for a row
    that isn't an impl."""
    head = re.match(r"(?:unsafe\s+)?impl\b", row)
    if not head:
        return ""
    rest, depth = "", 0
    for ch in row[head.end():].replace("->", "  "):  # leave out every generic argument
        depth += {"<": 1, ">": -1}.get(ch, 0)
        rest += ch if not depth and ch != ">" else ""
    rest = re.split(r"\bfor\b", rest)[-1] if re.search(r"\bfor\b", rest) else rest
    name = re.match(r"\s*(?:[&*]\s*(?:mut\s+)?)?(?:dyn\s+)?((?:\w+::)*\w+)", rest)
    return name[1].rsplit("::", 1)[-1] if name else ""


def block_end(rows: List[str], start: int) -> int:
    """The index of the row that closes the item opened on row `start`: that row when it ends in `;` or `}`, else
    the next row with `}` or `)` at its first column."""
    if rows[start].rstrip().endswith((";", "}")):
        return start
    return next((n for n in range(start + 1, len(rows)) if rows[n].startswith(("}", ")"))), len(rows) - 1)


def type_sizes(rows: List[str]) -> Dict[str, List[int]]:
    """Per type declared or implemented at the top level of the file, the line it is first seen on and its lines
    there: its declaration plus every impl of it. impls in other files aren't added."""
    sizes: Dict[str, List[int]] = {}
    n = 0
    while n < len(rows):
        found = TYPE_START.match(rows[n])
        name = found[1] if found else impl_target(rows[n])
        if not name:
            n += 1
            continue
        end = block_end(rows, n)
        sizes.setdefault(name, [n + 1, 0])[1] += end - n + 1
        n = end + 1
    return sizes


def line_smells(rows: List[str], start: int) -> Iterator[Tuple[int, str]]:
    """The 1-based line and smell of each row of cleaned code that holds one on its own: global state, an arm for
    any error and, from the test code at index `start` on, an assertion that any error passes."""
    for n, row in enumerate(rows):
        if GLOBAL.match(row):
            yield n + 1, "globals"
        if ANY_ERR_ARM.search(row):
            yield n + 1, "broad_catch"
        if n >= start and ANY_ERROR.search(row):
            yield n + 1, "broad_test_asserts"


def rust_text(r: Reader, rels: List[str], lim: Limits) -> None:
    """Add the rows read from the text of the Rust files `rels`."""
    for rel in rels:
        rows, comments = clean((r.root / rel).read_text(errors="replace"))
        for name, (line, size) in type_sizes(rows).items():
            r.add(rel, line, TYPE_LINES, size if size > lim[TYPE_LINES][0] else None, name)
        start = test_start(rel, rows)
        for line in magic_lines(rows, start):
            r.add(rel, line, "magic_numbers", 1)
        for line, comment in comments:
            if CODE_COMMENT.match(comment):
                r.add(rel, line, "commented_code", 1)
        for line in dropped_unwinds(rows):
            r.add(rel, line, "broad_catch", 1)
        for line, metric in line_smells(rows, start):
            r.add(rel, line, metric, 1)
