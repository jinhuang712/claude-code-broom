"""What one pass over a file gives `broom stats`: of a code file its code lines, test cases and skipped tests, lint
suppressions, TODO comments and unsafe code; of a YAML, shell or HTML file its lint suppressions; of a Markdown file
its links to paths that don't exist. No linter runs. Each language is read from its syntax tree: Swift's from its
compiler and SourceKit (swiftcalls), the others' from treefacts, Markdown's from its own small reader (mdlinks). A
marker counts only in a comment the tree isolated, never in a string."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Pattern, Set, Tuple

from .codelines import code_lines
from .mdlinks import broken
from .swiftcalls import skips, test_cases, unsafe_uses
from .swiftkit import comment_lines, open_text
from .testrot import TEST_FILE
from .treefacts import MARKUP_LANGS, TREE_LANGS, Tree, py_comments, py_tests
from .waivers import MARKERS, MARKUP_MARKERS


# The word as a marker in a comment: its first word, or followed by a colon or a bracket. "a TODO in the list" is
# prose, and so is a file's name such as TODO.md. It is tested only on a comment the tree isolated.
TODO_MARK = re.compile(r"^\W*(?:TODO|FIXME|HACK|XXX)\b(?![./-]\w)|\b(?:TODO|FIXME|HACK|XXX)[ \t]*[:(]")


MD_LANG = "md"
OTHER_LANGS = (*MARKUP_LANGS, MD_LANG)  # files that are no code: only their suppressions and their links are read


@dataclass
class Facts:
    """What `scan` found in one file: `rel` is its path from the repo root, `lines` its code lines, `test` whether
    it is a test file, `suppressions` the kind of each lint suppression, `todos` the line number of each TODO comment,
    `unsafe` how many unsafe constructs it holds, `broken_links` the line and destination of each Markdown link to a
    path that isn't there. A file of `OTHER_LANGS` is no code: no lines, no tests, no TODOs."""

    rel: str
    lang: str
    test: bool
    lines: int
    cases: int = 0
    skipped: int = 0
    suppressions: List[str] = field(default_factory=list)
    todos: List[int] = field(default_factory=list)
    unsafe: int = 0
    broken_links: List[Tuple[int, str]] = field(default_factory=list)
    read: bool = True  # False when its tree couldn't be read (no ast-grep): its counts are then unknown, not zero

    @property
    def code(self) -> bool:
        """Whether the file is code, as against a YAML, shell, HTML or Markdown file."""
        return self.lang not in OTHER_LANGS


def kind_of(marker: str) -> str:
    """A suppression's kind from its marker: `noqa`, `type: ignore`, `allow`..."""
    return "allow" if marker.startswith("#") else " ".join(marker.split())


def suppression_kinds(comments: List[str], markers: Pattern = MARKERS) -> List[str]:
    """The kind of each lint suppression in `comments`, the text of comments a tree isolated, one per comment line,
    by the `markers` of the file's kind of language."""
    return [kind_of(m.group()) for comment in comments for m in (markers.search(comment),) if m]


def python_tree(text: str, facts: Facts) -> Tree:
    """The tree of a Python file: its marked comments, and its cases and skips when `facts` say it is a test file."""
    tree = py_tests(text) if facts.test else Tree()
    tree.comments = py_comments(text)
    return tree


def from_tree(facts: Facts, tree: Optional[Tree]) -> Facts:
    """`facts` with what the file's tree shows: in a test file its cases and skips; a TODO comment where a comment's
    line holds a marker as `TODO_MARK` has it; a suppression for each comment line that holds a marker. With no tree
    the file is marked unread."""
    if tree is None:
        facts.read = False
        return facts
    if facts.test or facts.lang == "rust":  # Rust keeps its tests next to the code
        facts.cases, facts.skipped = tree.cases, len(tree.skips)
    lines = sorted(tree.comments.items())
    if facts.code:
        facts.todos = [n for n, comment in lines if TODO_MARK.search(comment)]
    facts.suppressions = suppression_kinds([comment for _, comment in lines], MARKERS if facts.code else MARKUP_MARKERS)
    facts.unsafe = min(tree.unsafe, 1) if facts.lang == "go" else tree.unsafe  # a Go file imports unsafe, or not
    return facts


def scan(rel: str, lang: str, text: str, tree: Optional[Tree] = None, lines: Optional[int] = None) -> Facts:
    """The facts of one file, from its `text`. A Python file is read from its tree here, a Swift file by its compiler,
    and a file of another language from `tree`, which ast-grep read for many files at once (treefacts.sg_trees).
    `lines` is how many code lines a code file holds, counted here when the caller hasn't (codelines, as a length
    counts). A Markdown file has no facts here: its links are checked against the repo (`link_facts`)."""
    other = lang in OTHER_LANGS
    if lines is None:
        lines = 0 if other else len(code_lines({rel: text}, [])[rel])
    facts = Facts(rel, lang, not other and bool(TEST_FILE.search(rel)), lines)
    if lang in TREE_LANGS or lang in MARKUP_LANGS:
        return from_tree(facts, python_tree(text, facts) if lang == "py" else tree)
    if lang == "swift":
        return swift_facts(facts, text)
    return facts


def link_facts(facts: Facts, text: str, known: Set[str]) -> Facts:
    """`facts` of a Markdown file with the line of each of its links to a path that isn't among `known`, the paths of
    the repo (mdlinks)."""
    facts.broken_links = broken(facts.rel, text, known)
    return facts


def swift_facts(facts: Facts, text: str) -> Facts:
    """`facts` with what a Swift file's tree and tokens hold (swiftcalls): its test cases and skipped tests, its unsafe
    code, and the suppressions and TODOs of its comments. Without SourceKit, none."""
    source = open_text(text)
    if source is None:
        return facts
    if facts.test:
        facts.cases, facts.skipped = test_cases(source), sum(1 for _ in skips(source))
    facts.unsafe = unsafe_uses(source)
    lines = comment_lines(source)
    facts.suppressions = suppression_kinds([comment for _, comment in lines])
    facts.todos = [n for n, comment in lines if TODO_MARK.search(comment)]
    return facts
