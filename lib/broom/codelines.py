"""The code lines of a file (decision 039): the lines that hold code. A length is a count of them, be it a file's, a
function's or a type's, so a comment line and a blank line never count, and adding one grows nothing.

A line holds code when something besides space stands on it outside a comment. The comments come from the file's
syntax tree, never from a pattern of its text (decision 038): Python's from the standard library's `tokenize`, with
the docstrings `ast` names; Swift's from SourceKit's tokens; Go's, TS/JS's, Rust's and CSS's from ast-grep's rules
`all-comments.yml` under `defaults/sg/rules/`. Where the comments can't be read (no ast-grep, no SourceKit), every
line that isn't blank counts, and the tool's note says so.
"""

from __future__ import annotations

import ast
import io
import tempfile
import tokenize
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .reading import TOOL_TIMEOUT
from .swiftkit import open_text
from .syntax import Rules, matches
from .toolchain import lang_of

COMMENTS = Rules(only="-all-comments$")
SG_LANGS = ("go", "js", "rust", "css")  # the languages whose comments ast-grep reads
BATCH = 2000  # files per ast-grep run, well inside the length of a command line
BLANKED = bytes(b if b in b"\n" else ord(" ") for b in range(256))  # every byte a space, but for the line break
# The tokens that are no code: a comment, and the line breaks and indentation the tokenizer reports.
QUIET = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
Lines = Dict[str, Set[int]]  # per file, its code lines (1-based)


def non_blank(text: str) -> Set[int]:
    """The lines of `text` (1-based) with something on them: its code lines where the comments can't be told."""
    return {n for n, row in enumerate(text.split("\n"), 1) if row.strip()}


def outside(data: bytes, spans: Iterable[Tuple[int, int]]) -> Set[int]:
    """The lines of `data` (1-based) that hold something besides space outside the byte ranges `spans`, each a first
    byte and the one after its last: the comments."""
    left = bytearray(data)
    for start, stop in spans:
        left[start:stop] = left[start:stop].translate(BLANKED)
    return {n for n, row in enumerate(bytes(left).split(b"\n"), 1) if row.strip()}


# ---------------------------------------------------------------- Python, in process


def docstrings(text: str) -> Set[Tuple[int, int]]:
    """Where each docstring of the Python source `text` starts, as (line, column): the string a module, a class or a
    function opens with. None for source that doesn't parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    firsts = [node.body[0] for node in ast.walk(tree) if isinstance(node, DOCUMENTED) and node.body]
    return {(first.lineno, first.col_offset) for first in firsts if isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)}


def python_code_lines(text: str) -> Set[int]:
    """The code lines of the Python source `text`: those a token stands on that is no comment and no docstring. Past
    a point the tokenizer can't read, every line that isn't blank counts."""
    docs = docstrings(text)
    filled = non_blank(text)
    code: Set[int] = set()
    read = 0  # the last line a token was read on
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            read = max(read, token.end[0])
            if token.type not in QUIET and not (token.type == tokenize.STRING and token.start in docs):
                code.update(range(token.start[0], token.end[0] + 1))
    except (tokenize.TokenError, SyntaxError):
        code.update(n for n in filled if n > read)
    return code & filled


# ---------------------------------------------------------------- Swift, by SourceKit


def swift_code_lines(text: str) -> Set[int]:
    """The code lines of the Swift source `text`, with the comments SourceKit's tokens give, doc comments among them;
    without SourceKit, every line that isn't blank."""
    source = open_text(text)
    if source is None:
        return non_blank(text)
    return outside(source.data, [(t.offset, t.offset + len(t.text.encode())) for t in source.tokens
                                 if "comment" in t.kind])


# ---------------------------------------------------------------- Go, TS/JS, Rust and CSS, by ast-grep


def sg_code_lines(root: Path, rels: List[str], notes: List[str]) -> Lines:
    """The code lines of the Go, TS/JS, Rust and CSS files `rels` under `root`, with the comments ast-grep's tree
    gives. Empty, with a note, when ast-grep is missing or a run of it failed."""
    mine: List[str] = []  # this run's own notes: other threads may add to `notes` meanwhile
    spans: Dict[str, List[Tuple[int, int]]] = {rel: [] for rel in rels}
    for start in range(0, len(rels), BATCH):
        for m in matches(root, rels[start:start + BATCH], mine, TOOL_TIMEOUT, COMMENTS):
            spans.setdefault(m.file, []).append((m.start, m.stop))
    notes += mine
    if mine:
        return {}
    out: Lines = {}
    for rel in rels:
        try:
            out[rel] = outside((root / rel).read_bytes(), spans[rel])
        except OSError:
            continue
    return out


READERS = {"py": python_code_lines, "swift": swift_code_lines}  # the languages read in broom's own process


def code_lines(texts: Dict[str, str], notes: List[str], root: Optional[Path] = None) -> Lines:
    """Per file of `texts` (a path to its text), its code lines. ast-grep reads files: those under `root` when the
    texts lie there at their paths, else copies in a scratch folder. A file whose comments couldn't be read, or of a
    language broom reads no tree of, gives every line that isn't blank."""
    sg = [rel for rel in texts if lang_of(Path(rel)) in SG_LANGS]
    if root is not None or not sg:
        out = sg_code_lines(root, sg, notes) if root is not None else {}
    else:
        with tempfile.TemporaryDirectory(prefix="broom-lines-") as tmp:
            for rel in sg:
                (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / rel).write_text(texts[rel], encoding="utf-8")
            out = sg_code_lines(Path(tmp), sg, notes)
    for rel, text in texts.items():
        if rel not in out:
            out[rel] = READERS.get(lang_of(Path(rel)) or "", non_blank)(text)
    return out


class CodeLines:
    """The code lines of files held in memory, read when first asked for: a check asks for the few files it has a
    question about, and each is read once."""

    def __init__(self, texts: Dict[str, str], notes: List[str]) -> None:
        self.texts, self.notes = texts, notes
        self.known: Lines = {}

    def of(self, rels: Iterable[str]) -> Lines:
        """The code lines of each of `rels` this holds the text of."""
        wanted = [rel for rel in rels if rel in self.texts]
        new = {rel: self.texts[rel] for rel in wanted if rel not in self.known}
        if new:
            self.known.update(code_lines(new, self.notes))
        return {rel: self.known[rel] for rel in wanted}
