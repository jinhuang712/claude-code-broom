"""What a file's syntax tree tells the check-up's counters, the skipped-test smell, the suppressions a change adds and
the header of generated code (decision 038): the comments that hold a marker word, the test cases, the skipped
tests, each with whether a condition decides it, and the unsafe code of Rust and Go. Python is read in broom's own process with the standard library's
`tokenize` and `ast`, Swift's comments by SourceKit, and Go, TS/JS, Rust and CSS by ast-grep's rules `*-tests.yml`
and `*-comments.yml` under `defaults/sg/rules/` (syntax.py), in one run for many files. The comments of YAML, shell and
HTML files, which hold no code smells, are read the same way, for their lint suppressions. Nothing here reads source text
by pattern: a comment's text is tested only once the tree has isolated it."""

from __future__ import annotations

import ast
import io
import tempfile
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .reading import TOOL_TIMEOUT
from .swiftkit import comment_lines, open_text
from .syntax import Match, Rules, by_file, matches, parsed
from .toolchain import lang_of, markup_of

TREE_LANGS = ("py", "go", "js", "rust", "css")  # the languages whose counters and skips come from a tree here
SG_LANGS = ("go", "js", "rust", "css")  # those ast-grep reads
MARKUP_LANGS = ("yaml", "shell", "html")  # files with no code smells read, whose comments ast-grep reads
FACT_RULES = Rules(only="(test-case|skip|comment|suppression|unparsed|unsafe)$")  # these facts' rules, none of the smells'
COMMENT_RULES = Rules(only="(comment|suppression)$")  # the comments alone, and Rust's `allow` attributes
BATCH = 2000  # files per ast-grep run, well inside the length of a command line
# The words of every TODO marker, lint suppression and generated header. A Python file with none of them holds no
# such comment, so it isn't tokenized; ast-grep's comment rules look for the same words.
WORDS = ("TODO", "FIXME", "HACK", "XXX", "noqa", "ignore", "disable", "nolint", "@ts-", "allow(", "DO NOT EDIT",
         "@generated")


@dataclass
class Tree:
    """What one file's tree shows: per line, the text of the comments with a marker word on it; how many test cases it
    holds; each skipped test as (line, whether a condition decides it); and how many unsafe constructs it holds."""

    comments: Dict[int, str] = field(default_factory=dict)
    cases: int = 0
    unsafe: int = 0
    skips: List[Tuple[int, bool]] = field(default_factory=list)

    def add(self, m: Match) -> None:
        """Add what the ast-grep match `m` found."""
        if m.smell == "marked_comment":
            for n, row in enumerate(m.caught.get("TEXT", "").split("\n"), m.line):
                self.comments[n] = f"{self.comments[n]} {row}" if n in self.comments else row
        elif m.smell == "test_case":
            self.cases += 1
        elif m.smell == "unsafe_code":
            self.unsafe += 1
        elif m.smell in ("skipped_test", "guarded_skip"):
            self.skips.append((m.line, m.smell == "guarded_skip"))


# ---------------------------------------------------------------- Python, in process

SKIP_DECORATORS = {"skip", "skipIf", "skipUnless", "skipif", "xfail"}
CONDITION_NAMED = {"skipIf", "skipUnless", "skipif"}
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
# What decides whether the code under it runs: an `if`, a conditional expression, an `except`, `and`/`or`, a `case`.
GUARDS = (ast.If, ast.IfExp, ast.ExceptHandler, ast.BoolOp, *((ast.match_case,) if hasattr(ast, "match_case") else ()))


def py_comments(text: str) -> Dict[int, str]:
    """Per line, the comment token on it, for a file that holds a marker word at all. Code past a point the tokenizer
    can't read is left out."""
    found: Dict[int, str] = {}
    if not any(word in text for word in WORDS):
        return found
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                found[token.start[0]] = token.string
    except (tokenize.TokenError, SyntaxError):
        pass
    return found


def last_name(node: ast.AST) -> str:
    """The name a decorator or a call goes by: `skip` for `unittest.skip`, `pytest.mark.skip` and `skip`."""
    node = node.func if isinstance(node, ast.Call) else node
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ""


def decorator_skip(d: ast.expr) -> Optional[bool]:
    """None when the decorator `d` skips nothing; else whether a condition decides it: its name says so
    (`skipIf`, `skipUnless`, `skipif`), or an `xfail` is given a condition."""
    name = last_name(d)
    if name not in SKIP_DECORATORS:
        return None
    if name in CONDITION_NAMED:
        return True
    return name == "xfail" and isinstance(d, ast.Call) and (bool(d.args) or any(k.arg == "condition" for k in d.keywords))


def is_skip_call(node: ast.AST) -> bool:
    """Whether `node` is a call that skips the test it runs in: `self.skipTest(...)` or `pytest.skip(...)`."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    owner = node.func.value
    return node.func.attr == "skipTest" or (node.func.attr == "skip" and isinstance(owner, ast.Name)
                                            and owner.id == "pytest")


def py_tests(text: str) -> Tree:
    """The test cases (`def test_...`) and skips of a Python file; nothing for one that doesn't parse."""
    tree = Tree()
    try:
        root = ast.parse(text)
    except (SyntaxError, ValueError):
        return tree
    stack: List[Tuple[ast.AST, bool]] = [(root, False)]
    while stack:
        node, guarded = stack.pop()
        if isinstance(node, DEFS):
            tree.cases += not isinstance(node, ast.ClassDef) and node.name.startswith("test_")
            tree.skips += [(d.lineno, guarded or bool(c)) for d in node.decorator_list
                           for c in (decorator_skip(d),) if c is not None]
        elif is_skip_call(node):
            tree.skips.append((node.lineno, guarded))
        inner = guarded or isinstance(node, GUARDS)
        stack += [(child, inner) for child in ast.iter_child_nodes(node)]
    tree.skips.sort()
    return tree


# ---------------------------------------------------------------- Go and TS/JS, by ast-grep


def sg_trees(root: Path, rels: List[str], notes: List[str], rules: Rules = FACT_RULES) -> Dict[str, Tree]:
    """The tree facts of the Go, TS/JS, Rust, CSS, YAML, shell and HTML files `rels` under `root`. Empty, with a note, when ast-grep is
    missing or a run of it failed: the files are then unread, not clean. What lies in a region the grammar can't read
    is left out, with a note."""
    found: List[Match] = []
    mine: List[str] = []  # this run's own notes: other threads may add to `notes` meanwhile
    for start in range(0, len(rels), BATCH):
        found += matches(root, rels[start:start + BATCH], mine, TOOL_TIMEOUT, rules)
    notes += mine
    if mine:
        return {}
    trees = {rel: Tree() for rel in rels}
    for rel, ms in parsed(by_file(found, rels), notes).items():
        for m in ms:
            if rel in trees:
                trees[rel].add(m)
    for tree in trees.values():
        tree.skips.sort()  # in line order: ast-grep gives each rule's matches in turn
    return trees


def skip_trees(texts: Dict[str, str], notes: List[str]) -> Dict[str, Tree]:
    """The test cases and skips of the test files `texts` (path to text) in a tree language. ast-grep reads files, so
    the Go and TS/JS ones are written to a scratch folder first; a file ast-grep couldn't read is missing."""
    out = {rel: py_tests(text) for rel, text in texts.items() if lang_of(Path(rel)) == "py"}
    sg = [rel for rel in texts if lang_of(Path(rel)) in SG_LANGS]
    if sg:
        with tempfile.TemporaryDirectory(prefix="broom-tree-") as tmp:
            for rel in sg:
                (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / rel).write_text(texts[rel], encoding="utf-8")
            out.update(sg_trees(Path(tmp), sg, notes))
    return out


def swift_comments(text: str) -> Dict[int, str]:
    """Per line, the text of the Swift comments on it, as SourceKit's tokens give them; none without SourceKit."""
    source = open_text(text)
    found: Dict[int, str] = {}
    for n, row in comment_lines(source) if source else []:
        found[n] = f"{found[n]} {row}" if n in found else row
    return found


def comment_trees(root: Path, texts: Dict[str, str], notes: List[str]) -> Dict[str, Dict[int, str]]:
    """Per file of `texts` (a path under `root` to its text), per line, the text of the comments on it that hold a
    marker word, and Rust's `allow` attributes: Python's from its tokens, Swift's from SourceKit's, the others' (YAML,
    shell and HTML included) from ast-grep, which reads them from `root`. A file of another language, or one whose tree
    couldn't be read, has none."""
    out: Dict[str, Dict[int, str]] = {}
    for rel, text in texts.items():
        lang = lang_of(Path(rel))
        if lang == "py":
            out[rel] = py_comments(text)
        elif lang == "swift":
            out[rel] = swift_comments(text)
    sg = [rel for rel in texts if lang_of(Path(rel)) in SG_LANGS or markup_of(Path(rel))]
    out.update((rel, tree.comments) for rel, tree in sg_trees(root, sg, notes, COMMENT_RULES).items())
    return out
