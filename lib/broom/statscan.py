"""What one pass over a code file gives `broom stats`: its non-blank lines, its test cases and skipped tests, its lint
suppressions and its TODO comments. No linter runs. Each language is read from its syntax tree: Swift's from its
compiler and SourceKit (swiftcalls), the others' from treefacts. A marker counts only in a comment the tree isolated,
never in a string."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .swiftcalls import skips, test_cases
from .swiftkit import comment_lines, open_text
from .testrot import TEST_FILE
from .treefacts import TREE_LANGS, Tree, py_comments, py_tests
from .waivers import MARKERS, suppression_in


# The word as a marker in a comment: its first word, or followed by a colon or a bracket. "a TODO in the list" is
# prose, and so is a file's name such as TODO.md. It is tested only on a comment the tree isolated.
TODO_MARK = re.compile(r"^\W*(?:TODO|FIXME|HACK|XXX)\b(?![./-]\w)|\b(?:TODO|FIXME|HACK|XXX)[ \t]*[:(]")


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
    read: bool = True  # False when its tree couldn't be read (no ast-grep): its counts are then unknown, not zero


def kind_of(marker: str) -> str:
    """A suppression's kind from its marker: `noqa`, `type: ignore`, `allow`..."""
    return "allow" if marker.startswith("#") else " ".join(marker.split())


def suppression_kinds(rows: List[str]) -> List[str]:
    """The kind of each lint suppression in `rows`, one per line that has one."""
    return [kind_of(k) for k in map(suppression_in, rows) if k]


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
    facts.todos = [n for n, comment in lines if TODO_MARK.search(comment)]
    facts.suppressions = [kind_of(m.group()) for _, comment in lines for m in (MARKERS.search(comment),) if m]
    return facts


def scan(rel: str, lang: str, text: str, tree: Optional[Tree] = None) -> Facts:
    """The facts of one file, from its `text`. A Python file is read from its tree here, a Swift file by its compiler,
    and a file of another language from `tree`, which ast-grep read for many files at once (treefacts.sg_trees)."""
    rows = text.splitlines()
    facts = Facts(rel, lang, bool(TEST_FILE.search(rel)), sum(1 for row in rows if row.strip()))
    if lang in TREE_LANGS:
        return from_tree(facts, python_tree(text, facts) if lang == "py" else tree)
    if lang == "swift":
        return swift_facts(facts, text)
    return facts


def swift_facts(facts: Facts, text: str) -> Facts:
    """`facts` with what a Swift file's tree and tokens hold (swiftcalls): its test cases and skipped tests, and the
    suppressions and TODOs of its comments. Without SourceKit, none."""
    source = open_text(text)
    if source is None:
        return facts
    if facts.test:
        facts.cases, facts.skipped = test_cases(source), sum(1 for _ in skips(source))
    lines = comment_lines(source)
    facts.suppressions = suppression_kinds([comment for _, comment in lines])
    facts.todos = [n for n, comment in lines if TODO_MARK.search(comment)]
    return facts
