"""Commented-out Swift code: a `//` comment that the Swift compiler parses as code. SourceKit's tokens say where the
comments are and whether a comment's text parses with no error (swiftkit), and swiftc's tree of a text that does says
what it holds (swifttree): it is code when a statement of it is a declaration, a control statement, a call of a named
function or an assignment. Prose doesn't parse, and a lone word, which does, is none of those. No keyword is matched, so `// if x is set, retry {see docs}`
is prose and `// x += 1` is code.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

from .swiftkit import comments, open_text, parses
from .swifttree import Tree, kind, name_of, parse

# What a statement of code is, and prose that happens to parse is not: a declaration or a control statement, an
# assignment, or a call of a named function (`f(x)`, `a.b(c)`), `try` or `await` before it or not. `nil-checked (A, b)`
# parses as a subtraction, and `[text](url)` as a call of an array: neither is a statement anyone writes.
STATEMENTS = {"func_decl", "pattern_binding_decl", "var_decl", "import_decl", "struct_decl", "class_decl", "enum_decl",
              "protocol_decl", "extension_decl", "typealias", "return_stmt", "if_stmt", "guard_stmt", "for_each_stmt",
              "while_stmt", "repeat_while_stmt", "switch_stmt", "do_stmt", "do_catch_stmt", "throw_stmt", "defer_stmt",
              "assign_expr", "macro_expansion_expr"}
NAMED = {"unresolved_decl_ref_expr", "unresolved_dot_expr", "unresolved_member_expr", "unresolved_specialize_expr"}
WRAPPERS = {"try_expr", "force_try_expr", "optional_try_expr", "await_expr"}
ASSIGNING = ("=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=")
Snippet = Tuple[str, int]  # the file a comment is in, and the line its code starts on


def statements(tree: Tree) -> Iterator[dict]:
    """The statements and declarations at the top of a parsed text."""
    for item in tree.items:
        if kind(item) == "top_level_code_decl":
            yield from (item.get("body") or {}).get("elements") or []
        else:
            yield item


def named_call(node: dict) -> bool:
    """Whether `node` calls a function by its name, through any chain of calls and members: `a.b(c).d()`."""
    while kind(node) in WRAPPERS:
        node = node.get("sub_expr") or {}
    if kind(node) != "call_expr":
        return False
    fn = node.get("fn") or {}
    while kind(fn) == "unresolved_dot_expr" and kind(fn.get("base") or {}) in ("call_expr", "unresolved_dot_expr"):
        fn = fn.get("base") or {}
    return kind(fn) in NAMED or named_call(fn)


def is_code(tree: Tree) -> bool:
    """Whether a comment's text, parsed as a file of its own, is code: no error, and a statement only code has."""
    return not tree.bad and any(
        kind(s) in STATEMENTS or named_call(s)
        or (kind(s) == "sequence_expr" and any(name_of(e) in ASSIGNING for e in s.get("elements") or []))
        for s in statements(tree))


def snippets(rel: str, text: str) -> Dict[Snippet, List[str]]:
    """The texts that parse, of one file's `//` comments, by where each starts: a run of them alone on lines that
    follow one another, else each of the run's lines alone, as a run may hold prose and code both."""
    source = open_text(text)
    out: Dict[Snippet, List[str]] = {}
    for run in comments(source) if source else []:
        if not run.slashes:
            continue
        bodies = [t.rstrip("\n")[2:] for t in run.texts if not t.startswith("///")]
        if len(bodies) > 1 and parses("\n".join(bodies)):
            out[(rel, -run.line)] = bodies  # the run as a whole: a negative line keeps it apart from its first line
        else:
            out.update({(rel, run.line + n): [body] for n, body in enumerate(bodies) if body.strip() and parses(body)})
    return out


def commented_code(root: Path, rels: List[str]) -> List[Tuple[str, int]]:
    """The (file, line) of each `//` comment in the Swift files `rels` under `root` that swiftc parses as code. A
    run of them that is code counts once, on its first line."""
    texts: Dict[Snippet, List[str]] = {}
    for rel in rels:
        texts.update(snippets(rel, (root / rel).read_text(errors="replace")))
    if not texts:
        return []
    keys = list(texts)
    with tempfile.TemporaryDirectory() as tmp:
        names = []
        for n, key in enumerate(keys):
            names.append(f"c{n}.swift")
            (Path(tmp) / names[-1]).write_text("\n".join(texts[key]) + "\n")
        trees = parse(Path(tmp), names, [])
    code = {key for key, name in zip(keys, names) if name in trees and is_code(trees[name])}
    runs = sorted((rel, -line) for rel, line in code if line < 0)
    inside = {(rel, line + n) for rel, line in runs for n in range(len(texts[(rel, -line)]))}
    return sorted(runs + [key for key in code if key[1] > 0 and key not in inside])
