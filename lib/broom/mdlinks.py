"""The links of a Markdown file, read from its structure and checked against the files of the repo. ast-grep has no
Markdown grammar, so this is a small reader of CommonMark's link nodes: it takes the text apart into what Markdown
itself does (fenced code, code spans, HTML comments and tags, link definitions, inline links and images), and a link
counts only where Markdown would make one, so a link in a code block or a code span is never one. Nothing here matches
text by pattern: it walks the characters, as a parser does.

Not read: indented code blocks (a four-space indent is as often a nested list as code), links written as HTML
`<a href>`, and a reference link with no definition, which Markdown shows as plain text.
"""

from __future__ import annotations

import bisect
import posixpath
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlsplit

FENCE_MIN = 3  # backticks or tildes that open a fenced code block
ORDINAL_DIGITS = 9  # the digits of an ordered list's number, at most
INDENT_MAX = 3  # a fence or a definition may be indented by up to this many spaces
FENCES = "`~"
LIST_MARKS = "-*+"
ESCAPABLE = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
Link = Tuple[int, str]  # the line of a link and its destination, as written


def block_content(line: str) -> str:
    """`line` less what a container puts before its content: block quote marks and a list marker, with the spaces."""
    rest = line.lstrip(" ")
    while rest[:1] == ">" or (rest[:1] in tuple(LIST_MARKS) and rest[1:2] == " "):
        rest = rest[1:].lstrip(" ")
    digits = len(rest) - len(rest.lstrip("0123456789"))
    if 0 < digits <= ORDINAL_DIGITS and rest[digits:digits + 1] in (".", ")") and rest[digits + 1:digits + 2] == " ":
        rest = rest[digits + 2:].lstrip(" ")
    return rest


def fence_of(line: str) -> Optional[Tuple[str, int]]:
    """The character and length of the fence `line` opens or closes, or None when it holds none."""
    rest = block_content(line)
    char = rest[:1]
    if char not in tuple(FENCES):
        return None
    run = len(rest) - len(rest.lstrip(char))
    info = rest[run:]
    return None if run < FENCE_MIN or (char == "`" and "`" in info) else (char, run)


def outside_fences(lines: List[str]) -> List[str]:
    """`lines` with each fenced code block, its fences included, emptied: the numbering of the lines stays."""
    kept: List[str] = []
    open_fence: Optional[Tuple[str, int]] = None
    for line in lines:
        fence = fence_of(line)
        if open_fence is None:
            open_fence = fence
            kept.append("" if fence else line)
            continue
        closing = fence is not None and fence[0] == open_fence[0] and fence[1] >= open_fence[1] \
            and not block_content(line).lstrip(open_fence[0]).strip()
        kept.append("")
        open_fence = None if closing else open_fence
    return kept


def definition_of(line: str) -> Optional[str]:
    """The destination of a link definition, `[label]: destination "title"`, that `line` is; None for any other line."""
    rest = line.lstrip(" ")
    if len(line) - len(rest) > INDENT_MAX or rest[:1] != "[" or rest[1:2] == "^":  # `[^1]:` is a footnote
        return None
    close = rest.find("]:")
    if close < 0 or not rest[1:close] or any(c in rest[1:close] for c in "[]"):
        return None
    tail = rest[close + 2:].strip()
    if tail[:1] == "<":
        end = tail.find(">")
        return tail[1:end] if end > 0 else None
    return tail.split()[0] if tail else None


class Inline:
    """The inline content of a text with its fences emptied and its definition lines left out: it finds the links."""

    def __init__(self, body: str) -> None:
        self.body = body
        self.found: List[Tuple[int, str]] = []  # the offset of each link's `[`, and its destination
        self.consumed: Dict[int, int] = {}  # where a link's `](...)` begins, and where it ends

    def paragraph_end(self, at: int) -> int:
        """The offset where the paragraph holding `at` ends: the next blank line, or the end of the text."""
        end = self.body.find("\n\n", at)
        return len(self.body) if end < 0 else end

    def line_end(self, at: int) -> int:
        """The offset where the line holding `at` ends."""
        end = self.body.find("\n", at)
        return len(self.body) if end < 0 else end

    def skip_code(self, at: int) -> int:
        """The offset after the code span that starts at `at`, a run of backticks to the next run as long; after the
        run alone when nothing closes it."""
        size = len(self.body[at:]) - len(self.body[at:].lstrip("`"))
        end, scan = self.paragraph_end(at), at + size
        while scan < end:
            if self.body[scan] != "`":
                scan += 1
                continue
            run = len(self.body[scan:end]) - len(self.body[scan:end].lstrip("`"))
            if run == size:
                return scan + run
            scan += run
        return at + size

    def skip_tag(self, at: int) -> int:
        """The offset after the HTML comment, tag or autolink that starts at `at`; `at + 1` when it is none."""
        if self.body.startswith("<!--", at):
            end = self.body.find("-->", at + len("<!--"))
            return len(self.body) if end < 0 else end + len("-->")
        after = self.body[at + 1:at + 2]
        end = self.body.find(">", at, self.paragraph_end(at))
        return end + 1 if end > 0 and (after.isalpha() or after in ("/", "!")) else at + 1

    def matching_bracket(self, at: int) -> int:
        """The offset of the `]` that closes the `[` at `at`, or -1: brackets nest, and code spans and escapes hide
        theirs."""
        depth, scan, end = 0, at, self.paragraph_end(at)
        while scan < end:
            char = self.body[scan]
            if char == "\\":
                scan += 2
                continue
            if char == "`":
                scan = self.skip_code(scan)
                continue
            depth += (char == "[") - (char == "]")
            if depth == 0:
                return scan
            scan += 1
        return -1

    def destination(self, at: int) -> Optional[Tuple[str, int]]:
        """The destination of the inline link whose `(` is at `at`, and the offset after its `)`; None when what
        follows is no inline link: a destination, then an optional title, then `)`."""
        scan = self.skip_space(at + 1)
        if self.body[scan:scan + 1] == "<":
            end = self.body.find(">", scan, self.line_end(scan))
            if end < 0:
                return None
            dest, scan = self.body[scan + 1:end], end + 1
        else:
            dest, scan = self.bare_destination(scan)
        scan = self.skip_space(scan)
        if self.body[scan:scan + 1] in ("\"", "'", "("):
            scan = self.skip_title(scan)
        scan = self.skip_space(scan)
        return (unescape(dest), scan + 1) if self.body[scan:scan + 1] == ")" else None

    def bare_destination(self, at: int) -> Tuple[str, int]:
        """A destination without angle brackets, from `at`: up to a space, or the `)` that no `(` of it opened."""
        depth, scan = 0, at
        while scan < len(self.body) and not self.body[scan].isspace():
            char = self.body[scan]
            if char == "\\":
                scan += 1
            elif char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            scan += 1
        return self.body[at:scan], scan

    def skip_title(self, at: int) -> int:
        """The offset after the link title that starts at `at`, in quotes or parentheses; `at` when it never ends."""
        closer = ")" if self.body[at] == "(" else self.body[at]
        scan, end = at + 1, self.paragraph_end(at)
        while scan < end:
            if self.body[scan] == "\\":
                scan += 1
            elif self.body[scan] == closer:
                return scan + 1
            scan += 1
        return at

    def skip_space(self, at: int) -> int:
        """The offset of the first character from `at` that is no space or line break."""
        return at + len(self.body[at:]) - len(self.body[at:].lstrip())

    def link_at(self, at: int) -> None:
        """Note the inline link or image whose `[` is at `at`, if it is one, and where its `](...)` lies."""
        close = self.matching_bracket(at)
        if close < 0 or self.body[close + 1:close + 2] != "(":
            return
        read = self.destination(close + 1)
        if read:
            self.found.append((at, read[0]))
            self.consumed[close] = read[1]

    def step(self, at: int) -> int:
        """The offset to go on from after the character at `at`: past an escape, a code span or a tag, or just the
        next one. An opening bracket is looked at for a link, and the text of the link is read on."""
        char = self.body[at]
        if char == "[":
            self.link_at(at)
        if char == "\\":
            return at + 2
        if char == "`":
            return self.skip_code(at)
        return self.skip_tag(at) if char == "<" else at + 1

    def read(self) -> List[Tuple[int, str]]:
        """Every link of the text, as (offset of its `[`, destination)."""
        scan = 0
        while scan < len(self.body):
            scan = self.consumed[scan] if scan in self.consumed else self.step(scan)
        return self.found


def unescape(dest: str) -> str:
    """`dest` with the backslash of each escaped punctuation mark taken out."""
    out, scan = [], 0
    while scan < len(dest):
        if dest[scan] == "\\" and scan + 1 < len(dest) and dest[scan + 1] in ESCAPABLE:
            scan += 1
        out.append(dest[scan])
        scan += 1
    return "".join(out)


def links(text: str) -> List[Link]:
    """The (line, destination) of every link, image and link definition in the Markdown `text`, by line: not those in
    fenced code, a code span, an HTML comment or tag."""
    lines = outside_fences(text.split("\n"))
    found: List[Link] = []
    body: List[str] = []
    for n, line in enumerate(lines, 1):
        dest = definition_of(line)
        if dest is not None:
            found.append((n, dest))
        body.append("" if dest is not None or not line.strip() else line)
    starts = [0]
    for line in body:
        starts.append(starts[-1] + len(line) + 1)
    inline = Inline("\n".join(body)).read()
    return sorted(found + [(bisect.bisect_right(starts, offset), dest) for offset, dest in inline], key=lambda link: link[0])


# ---------------------------------------------------------------- against the repo


def target(dest: str, rel: str) -> Optional[str]:
    """The path from the repo root a destination written in the Markdown file `rel` points at; None for a destination
    that isn't a relative path: an anchor in the same file, a URL with a scheme, a `//host`, a path from the root of a
    site (`/x`), or nothing. A query and an anchor are taken off, and percent-encoding is undone."""
    parts = urlsplit(dest.strip())
    path = unquote(parts.path)
    if parts.scheme or parts.netloc or not path or path.startswith("/"):
        return None
    return posixpath.normpath(posixpath.join(posixpath.dirname(rel), path))


def known_paths(files: List[str]) -> Set[str]:
    """The paths of `files` and of every folder above them, with `.` for the root: what a link may point at."""
    known = {"."}
    for rel in files:
        parts = rel.split("/")
        known.update("/".join(parts[:n]) for n in range(1, len(parts) + 1))
    return known


def broken(rel: str, text: str, known: Set[str]) -> List[Link]:
    """The (line, destination as written) of each link of the Markdown file `rel` (its `text`) that points at a
    relative path not in `known`."""
    return [(line, dest) for line, dest in links(text) if (path := target(dest, rel)) is not None and path not in known]
