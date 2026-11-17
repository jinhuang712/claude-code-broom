"""What one pass over a code file's text gives `broom stats`: its non-blank lines, its test cases and skipped tests, its
lint suppressions and its TODO comments. Plain counting, by each language's own forms; no linter or parser runs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Pattern, Tuple

from .testrot import SKIPS, TEST_FILE
from .waivers import MARKERS, suppression_in


def rx(pattern: str) -> Pattern[str]:
    """A pattern whose `^` and `$` match at each line."""
    return re.compile(pattern, re.M)


# Per language: how a test case is written, and how one is skipped (testrot). Go, Python, JS/TS and Swift are read in
# test files only (`it(` and `.disabled` mean other things elsewhere); Rust keeps its tests next to the code.
FORMS: Dict[str, Tuple[Pattern[str], Pattern[str]]] = {
    "py": (rx(r"^[ \t]*(?:async[ \t]+)?def[ \t]+test_"), SKIPS["py"]),
    "js": (rx(r"(?<![\w.$])(?:x?it|x?test)(?:\.(?:only|skip|each|concurrent|fails))?[ \t]*\("), SKIPS["js"]),
    "go": (rx(r"^func[ \t]+Test\w*[ \t]*\("), SKIPS["go"]),
    "rust": (rx(r"#\[(?:\w+::)*test\b[^\]]*\]"), SKIPS["rust"]),
    "swift": (rx(r"^[ \t]*(?:@\w+[ \t]+)*func[ \t]+test\w*[ \t]*\(|^[ \t]*@Test\b"), SKIPS["swift"]),
}
TODO_WORD = re.compile(r"\b(?:TODO|FIXME|HACK|XXX)\b")
# The word as a marker in a comment: its first word, or followed by a colon or a bracket. "a TODO in the list" is
# prose, and so is a file's name such as TODO.md.
TODO_MARK = re.compile(r"^\W*(?:TODO|FIXME|HACK|XXX)\b(?![./-]\w)|\b(?:TODO|FIXME|HACK|XXX)[ \t]*[:(]")
STRING = r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'"  # a string that ends on its line
# What opens a comment or a string that may run past its line, per language: opener -> (closer, is a comment).
BLOCKS: Dict[str, Dict[str, Tuple[str, bool]]] = {
    "py": {'"""': ('"""', False), "'''": ("'''", False)},
    "js": {"/*": ("*/", True), "`": ("`", False)},
    "go": {"/*": ("*/", True), "`": ("`", False)},
    "rust": {"/*": ("*/", True)},
    "swift": {"/*": ("*/", True), '"""': ('"""', False)},
    "css": {"/*": ("*/", True)},
}


@dataclass
class Facts:
    """What `scan` found in one file: `rel` is its path from the repo root, `lines` its non-blank lines, `test` whether
    it is a test file, `suppressions` the kind of each lint suppression, `todos` the line number of each TODO comment."""

    rel: str
    lang: str
    test: bool
    lines: int
    cases: int = 0
    skipped: int = 0
    suppressions: List[str] = field(default_factory=list)
    todos: List[int] = field(default_factory=list)


class Comments:
    """Splits the lines of one file, fed in order, into code and comment: a comment sign inside a string is no comment,
    and a block comment or a multi-line string that a line leaves open carries over to the next."""

    def __init__(self, lang: str) -> None:
        self.blocks = BLOCKS.get(lang, {})
        self.sign = "#" if lang == "py" else "//"
        self.tokens = re.compile("|".join([*map(re.escape, self.blocks), STRING, re.escape(self.sign)]))
        self.closer: Optional[str] = None  # what ends the comment or string a line left open
        self.comment = False  # whether that is a comment

    def skip(self, line: str, pos: int, found: List[str]) -> int:
        """Where the open comment or string ends on `line` (its end when it goes on), with the comment's text added to
        `found`."""
        closer = self.closer or ""
        end = line.find(closer, pos)
        if self.comment:
            found.append(line[pos:] if end < 0 else line[pos:end])
        if end < 0:
            return len(line)
        self.closer = None
        return end + len(closer)

    def of(self, line: str) -> str:
        """The comment text on `line`: what follows a comment sign, and what a block comment holds."""
        found: List[str] = []
        pos = 0
        while pos < len(line):
            if self.closer:
                pos = self.skip(line, pos, found)
                continue
            m = self.tokens.search(line, pos)
            if not m:
                break
            pos = m.end()
            if m.group() == self.sign:
                found.append(line[pos:])
                break
            if m.group() in self.blocks:
                self.closer, self.comment = self.blocks[m.group()]
        return " ".join(found)


def todo_lines(lang: str, rows: List[str]) -> List[int]:
    """The numbers of the lines whose comment is marked TODO, FIXME, HACK or XXX: the word opens the comment, or a
    colon or a bracket follows it. One in a string doesn't count, and neither does one in a comment's prose."""
    comments = Comments(lang)
    return [n for n, row in enumerate(rows, 1) if TODO_MARK.search(comments.of(row))]


def suppression_kinds(rows: List[str]) -> List[str]:
    """The kind of each lint suppression in `rows`, one per line that has one: `noqa`, `type: ignore`, `allow`..."""
    kinds = [suppression_in(row) for row in rows]
    return ["allow" if k.startswith("#") else " ".join(k.split()) for k in kinds if k]


def count_tests(lang: str, text: str) -> Tuple[int, int]:
    """(test cases, skipped tests) in `text`, by the language's own forms."""
    form = FORMS.get(lang)
    return (len(form[0].findall(text)), len(form[1].findall(text))) if form else (0, 0)


def scan(rel: str, lang: str, text: str) -> Facts:
    """The facts of one file, from its `text`. A marker or a TODO word is looked for in the whole text first, so a file
    without one is never read line by line."""
    rows = text.splitlines()
    facts = Facts(rel, lang, bool(TEST_FILE.search(rel)), sum(1 for row in rows if row.strip()))
    if facts.test or lang == "rust":
        facts.cases, facts.skipped = count_tests(lang, text)
    if MARKERS.search(text):
        facts.suppressions = suppression_kinds(rows)
    if TODO_WORD.search(text):
        facts.todos = todo_lines(lang, rows)
    return facts
