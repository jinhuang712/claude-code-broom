"""What broom reads from Swift source itself, for the smells SwiftLint has no rule for: control flow nested too deep
in a function, a catch that never looks at its error, and a private declaration nothing in its file names.

The text is read with its comments and string literals blanked first (raw `#"…"#`, multi-line `\"\"\"` and the
`\\( )` interpolation inside them included), so a brace in either never counts. What is left is counted brace by
brace: the line that opens a block says what it is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .reading import Limits, Reader
from .toolchain import SWIFT_EXTS

STRING_START = re.compile(r'(#*)("""|")')
# What opens a control-flow block, after an optional label: `outer: for x in xs {`. `guard … else` is left out, as
# it is how Swift keeps code flat; `else` and `catch` stand where their `if` and `do` stood.
CONTROL = re.compile(r"(?:\w+\s*:\s*)?(?:\}\s*)?(if|for|while|switch|repeat|do|catch|else)\b")
# What starts a function: its body resets the depth, as a nested function is read on its own.
FUNCTION = re.compile(r"(?:[@\w()]+\s+)*?(?:func\s+(\w+|[^\s(]+)|(init|deinit|subscript)\b)")
CONTINUED = (",", "&&", "||", "(", "=")  # a line that ends so goes on to the next
# `catch {`, `catch _ {`, `catch let e {`: a catch of every error, and the name it is bound to (`error` when none is).
BROAD_CATCH = re.compile(r"catch(?:\s+_|\s+(?:let|var)\s+(\w+))?\s*$")
# A private declaration and its name; `private(set)` only hides a setter.
PRIVATE = re.compile(r"\b(?:private|fileprivate)\s+(?:(?:static|class|final|lazy|mutating|nonisolated|override|"
                     r"weak|unowned|convenience|required|indirect)\s+)*"
                     r"(func|var|let|class|struct|enum|actor|protocol|typealias)\s+`?(\w+)")
KEPT = re.compile(r"@objc|@IB\w+|@NSManaged|\boverride\b|\bdynamic\b")  # used from outside the source's sight
IMPLICIT = {"CodingKeys"}  # named by the compiler, never by the code


# ---------------------------------------------------------------- blanking


def blank(src: str) -> str:
    """`src` with every comment and string literal turned to spaces, its newlines kept, so lines and columns match."""
    out = list(src)
    code_end(src, 0, out)
    return "".join(out)


def wipe(out: Optional[List[str]], start: int, end: int) -> None:
    """Blank `out[start:end]` but its newlines; nothing when `out` is None."""
    if out is not None:
        out[start:end] = [c if c == "\n" else " " for c in out[start:end]]


def code_end(src: str, i: int, out: Optional[List[str]], closer: str = "") -> int:
    """Read code from `i`, blanking comments and strings in `out`. With `closer` `)`, the code is an interpolation:
    it ends after the `)` that closes it, and the index past that is returned; else the end of `src`."""
    depth = 0
    while i < len(src):
        start = STRING_START.match(src, i) if src[i] in '"#' else None
        if src.startswith("//", i):
            end = src.find("\n", i)
            end = len(src) if end < 0 else end
        elif src.startswith("/*", i):
            end = comment_end(src, i)
        elif start:
            end = string_end(src, start.end(), start[1], start[2])
        else:
            if src[i] == closer and not depth:
                return i + 1
            depth += {"(": 1, ")": -1}.get(src[i], 0)
            i += 1
            continue
        wipe(out, i, end)
        i = end
    return i


def comment_end(src: str, i: int) -> int:
    """The index past the `*/` that closes the block comment opened at `i`; Swift's block comments nest."""
    depth = 0
    while i < len(src):
        if src.startswith("/*", i):
            depth, i = depth + 1, i + 2
        elif src.startswith("*/", i):
            depth, i = depth - 1, i + 2
            if not depth:
                return i
        else:
            i += 1
    return i


def string_end(src: str, i: int, hashes: str, quote: str) -> int:
    """The index past the string literal whose text starts at `i`: `hashes` is a raw string's `#`s, `quote` `"` or
    `\"\"\"`. An interpolation is read as code, so a `"` inside it doesn't end the string."""
    escape, close = "\\" + hashes, quote + hashes
    while i < len(src):
        if src.startswith(escape, i):
            i += len(escape)
            i = code_end(src, i + 1, None, ")") if src.startswith("(", i) else i + 1
        elif src.startswith(close, i):
            return i + len(close)
        elif src[i] == "\n" and quote == '"':
            return i  # a one-line string left open: the line ends it
        else:
            i += 1
    return i


# ---------------------------------------------------------------- blocks


@dataclass
class Block:
    """An open `{`: where it is in the text and on which line, the statement it opens, and what that is."""
    start: int
    line: int
    head: str
    control: bool = False
    function: Optional[str] = None
    end: int = -1  # where its `}` is, once read


GROUP = re.compile(r"\([^()]*\)|\[[^\[\]]*\]")


def statement_head(rows: List[str], line: int, col: int) -> str:
    """The statement a `{` at (`line`, `col`) opens, from its own line and the lines it continues; "" for a closure
    passed inside parentheses, as in `if xs.contains(where: { … })`."""
    head = rows[line][:col]
    n = line
    while n > 0 and rows[n - 1].rstrip().endswith(CONTINUED) and not re.search(r"[{};]\s*$", rows[n - 1]):
        n -= 1
        head = rows[n] + " " + head
    while GROUP.search(head):
        head = GROUP.sub(" ", head)
    return "" if re.search(r"[(\[]", head) else re.split(r"[{};]", head)[-1].strip()


def blocks(code: str) -> List[Block]:
    """Each block of the blanked `code`, in the order its `{` comes, its end set where its `}` is."""
    rows = code.split("\n")
    stack: List[Block] = []
    out: List[Block] = []
    offset = 0
    for n, row in enumerate(rows):
        for col, c in enumerate(row):
            if c == "{":
                head = statement_head(rows, n, col)
                fn = FUNCTION.match(head)
                block = Block(offset + col, n + 1, head, bool(CONTROL.match(head)) and not fn,
                              (fn[1] or fn[2]) if fn else None)
                out.append(block)
                stack.append(block)
            elif c == "}" and stack:
                stack.pop().end = offset + col
        offset += len(row) + 1
    return out


def nesting(code: str) -> Dict[Tuple[int, Optional[str]], int]:
    """Per function (its line and name; line 0 for code outside any), the deepest its control flow nests: the
    control-flow blocks open around a block, up to the function it is in."""
    deepest: Dict[Tuple[int, Optional[str]], int] = {}
    stack: List[Block] = []
    for block in blocks(code):
        while stack and not stack[-1].start < block.start < stack[-1].end:
            stack.pop()
        stack.append(block)
        if not block.control:
            continue
        owner = next((b for b in reversed(stack) if b.function), None)
        inner = stack[stack.index(owner) + 1:] if owner else stack
        key = (owner.line, owner.function) if owner else (0, None)
        deepest[key] = max(deepest.get(key, 0), sum(b.control for b in inner))
    return deepest


def broad_catches(code: str) -> List[int]:
    """The lines of the catches of every error whose body never names the error and never throws; an empty one is
    a swallowed error instead."""
    found = []
    for block in blocks(code):
        m = BROAD_CATCH.search(block.head)
        body = code[block.start + 1:block.end]
        if not (m and CONTROL.match(block.head)) or block.end < 0 or not body.strip():
            continue
        name = m[1] or (None if "_" in block.head else "error")
        if not re.search(r"\bthrow\b", body) and not (name and re.search(rf"\b{name}\b", body)):
            found.append(block.line)
    return found


def unused_private(src: str) -> List[Tuple[int, str]]:
    """The private and fileprivate declarations whose name appears nowhere else in the file, as (line, what):
    nothing outside the file can use them. A name in a comment or a string counts as a use, to be safe."""
    code = blank(src)
    out = []
    for m in PRIVATE.finditer(code):
        name = m[2]
        line = code.count("\n", 0, m.start()) + 1
        before = code[code.rfind("\n", 0, m.start()) + 1:m.start()]
        above = code[:m.start() - len(before)].rstrip("\n").rsplit("\n", 1)[-1]
        before += above if above.strip().startswith("@") else ""
        if name in IMPLICIT or KEPT.search(before) or len(re.findall(rf"\b{name}\b", src)) > 1:
            continue
        out.append((line, f"{m[1]} {name}"))
    return out


def swift_unused(repo: Path, rels: List[str]) -> List[Tuple[str, int, str]]:
    """The private declarations nothing in their file names, in the Swift files `rels` of the real tree, as (rel,
    line, what): the real tree's, so that smells.py keeps those on the lines a change added, as for other dead code."""
    return [(rel, line, what) for rel in rels if Path(rel).suffix in SWIFT_EXTS and (repo / rel).is_file()
            for line, what in unused_private((repo / rel).read_text(errors="replace"))]


def swift_text(r: Reader, rels: List[str], lim: Limits) -> None:
    """Add the rows read from the text of the Swift files `rels`: a function nested past its limit and a catch
    that never looks at its error."""
    for rel in rels:
        code = blank((r.root / rel).read_text(errors="replace"))
        for (line, name), depth in nesting(code).items():
            r.add(rel, line or 1, "nesting", depth if depth > lim["nesting"][0] else None, name or "top level")
        for line in broad_catches(code):
            r.add(rel, line, "broad_catch", 1)
