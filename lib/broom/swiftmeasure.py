"""What broom reads from Swift's syntax tree (swifttree), for the smells SwiftLint has no rule for: control flow
nested too deep in a function, a catch that never looks at its error, a ternary inside a ternary and a file-level
`var`. The calls, parameters, comments and private names come from SourceKit's view of the same parser (swiftcalls,
swiftcomments).

Each is a kind of node, never a pattern in the text, so a brace or a `catch` in a string or a comment is never one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from .reading import Limits, Reader
from .smell import nothing_key
from .swiftcalls import broad_asserts, empty_tests, file_smells, unused_private
from .swiftcomments import commented_code
from .swiftkit import MISSING as SOURCEKIT_MISSING
from .swiftkit import SwiftFile, library, open_text
from .swifttree import Tree, children, kind, name_of, parse, walk
from .testrot import TEST_FILE
from .toolchain import SWIFT_EXTS

FUNCTIONS = {"func_decl", "constructor_decl", "destructor_decl", "accessor_decl"}
STORAGE = {"var_decl", "subscript_decl"}  # what an accessor belongs to
BODIES = FUNCTIONS | {"subscript_decl"}  # what SwiftLint measures the length of, with the accessors it never does
# What nests control flow. `guard … else` is left out, as it is how Swift keeps code flat; an `else if` stands where
# its `if` stood, and a `catch` where its `do` did.
CONTROL = {"if_stmt", "for_each_stmt", "while_stmt", "repeat_while_stmt", "switch_stmt", "do_stmt", "do_catch_stmt"}
COMPARISONS = {"==", "!=", "<=", ">=", "===", "!=="}  # operators that end in `=` and assign nothing
Key = Tuple[int, Optional[str]]  # a function's line and name; (0, None) for code outside any


def node_name(node: dict) -> str:
    """The name a declaration carries: its base name, or `init`, `deinit` or `subscript`."""
    name = node.get("name")
    special = ((name.get("base_name") or {}).get("special") if isinstance(name, dict) else None)
    return name_of(node) or str(special or "")


@dataclass
class Place:
    """Where a walk is: the function it is in, its key, the depth of control flow around it, the last line a node
    gave, and the storage an accessor below belongs to."""
    key: Key
    depth: int
    line: int
    storage: str = ""


def nesting(tree: Tree) -> Dict[Key, int]:
    """Per function, the deepest its control flow nests: the control-flow statements around a statement, up to the
    function it is in. A closure adds none, and a function inside a function is read on its own."""
    deepest: Dict[Key, int] = {}

    def visit(node: dict, place: Place, parent: str = "", slot: str = "") -> None:
        k = kind(node)
        span = tree.lines(node)
        line = span[0] if span else place.line
        if k in FUNCTIONS:
            name = place.storage if k == "accessor_decl" else node_name(node)
            place = Place((line, name or None), 0, line)
        elif k in CONTROL and not (k == "if_stmt" and parent == "if_stmt" and slot == "else_stmt"):
            place = Place(place.key, place.depth + 1, line, place.storage)
            deepest[place.key] = max(deepest.get(place.key, 0), place.depth)
        elif k in STORAGE:
            place = Place(place.key, place.depth, line, node_name(node))
        for key, child in children(node):
            visit(child, place, k, key)

    for item in tree.items:
        visit(item, Place((0, None), 0, 0))
    return deepest


def bound_name(clause: dict) -> Tuple[bool, Optional[str]]:
    """Whether the catch clause catches every error, and the name it binds the error to (`error` when it names none,
    None for `catch _`). `catch let e as T`, `catch is T`, `catch E.x` and `catch where …` catch some."""
    items = [c for key, c in children(clause) if key == "case_label_items"]
    if len(items) != 1 or items[0].get("where_expr"):
        return False, None
    pattern = items[0].get("pattern") or {}
    if kind(pattern) == "pattern_any":
        return True, None
    if kind(pattern) == "pattern_expr":
        return kind(pattern.get("sub_expr") or {}) == "discard_assignment_expr", None
    sub = pattern.get("sub_pattern") or {}
    if kind(pattern) == "pattern_binding" and kind(sub) == "pattern_named":
        return True, name_of(sub) or "error"
    return False, None


def broad_catches(tree: Tree) -> List[int]:
    """The lines of the catches of every error whose body never names the error and never throws; an empty one is
    a swallowed error instead."""
    clauses = [c for item in tree.items for node in walk(item) if kind(node) == "do_catch_stmt"
               for key, c in children(node) if key == "catch_stmts"]
    found = []
    for clause in clauses:
        broad, name = bound_name(clause)
        body = clause.get("body") or {}
        if broad and body.get("elements") and not any(
                kind(n) == "throw_stmt" or (name and name_of(n) == name and kind(n).endswith("_expr"))
                for n in walk(body)):
            found.append((tree.lines(clause) or (0, 0))[0])
    return found


def assigns(node: dict) -> bool:
    """Whether an element of an unfolded sequence assigns: `=`, or an operator such as `+=`."""
    if kind(node) == "assign_expr":
        return True
    name = name_of(node)
    return kind(node) == "unresolved_decl_ref_expr" and name.endswith("=") and name not in COMPARISONS


def ternaries_in(node: dict) -> int:
    """How many ternaries are in `node` and under it."""
    return sum(kind(n) == "ternary_expr" for n in walk(node))


def mentions(node: dict, text: str) -> int:
    """How many tokens naming `text` the node stands for: its name, member, type or argument label. A var_decl the
    parser adds beside its pattern, and any node it makes up, stands for none."""
    if node.get("implicit") or kind(node) == "var_decl":
        return 0
    return sum(value == text for value in (name_of(node), node.get("field"), node.get("id"), node.get("label")))


def anchor(source: Optional[SwiftFile], ancestor: dict, part: List[dict]) -> Optional[int]:
    """The line where the expression `part` starts, inside `ancestor`, the nearest node with a range: an expression
    has none, so its first name is found among SourceKit's tokens, the as many-th of that text as the tree has
    before it. None when it can't be told."""
    first = next((n for e in part for n in walk(e) if kind(n) == "unresolved_decl_ref_expr"
                  and name_of(n)[:1].isidentifier()), None)
    span = ancestor.get("range") or {}
    if source is None or first is None or "start" not in span:
        return None
    text = name_of(first)
    before = 0
    for n in walk(ancestor):
        if n is first:
            break
        before += mentions(n, text)
    hits = [t.offset for t in source.tokens if t.kind in ("identifier", "typeidentifier") and t.text.strip("`") == text
            and int(span["start"]) <= t.offset <= int(span.get("end", span["start"]))]
    return source.line(hits[before]) if before < len(hits) else None


def nested_ternaries(tree: Tree, source: Optional[SwiftFile] = None) -> List[int]:
    """The lines of the expressions that hold a ternary inside a ternary: its condition, either branch, or a second
    ternary in the same expression. The parser leaves an expression unfolded, so the ternary's condition and else
    branch are its neighbours in the sequence, after the last assignment. With SourceKit's tokens of the file
    (`source`), the line is the expression's own, else that of the statement around it."""
    found = []

    def visit(node: dict, ancestor: dict) -> None:
        ancestor = node if tree.lines(node) else ancestor
        if kind(node) == "sequence_expr":
            elements = node.get("elements") or []
            part = elements[max((i + 1 for i, e in enumerate(elements) if assigns(e)), default=0):]
            if any(kind(e) == "ternary_expr" for e in part) and sum(ternaries_in(e) for e in part) > 1:
                found.append(anchor(source, ancestor, part) or (tree.lines(ancestor) or (0, 0))[0])
        for _, child in children(node):
            visit(child, ancestor)

    for item in tree.items:
        visit(item, item)
    return sorted(set(found))


def globals_in(tree: Tree) -> Iterator[int]:
    """The lines of the file-level `var`s; a script's main.swift is made of them."""
    if Path(tree.rel).name == "main.swift":
        return
    for item in tree.items:
        if kind(item) == "var_decl" and item.get("top_level_global") and not item.get("let"):
            yield (tree.lines(item) or (0, 0))[0]


def function_spans(tree: Tree) -> List[Tuple[int, int]]:
    """The first and last line of every function, initializer, deinitializer, accessor and subscript the tree gives a
    range."""
    return [span for item in tree.items for node in walk(item) if kind(node) in BODIES
            for span in [tree.lines(node)] if span]


def span_from(spans: List[Tuple[int, int]], line: int) -> int:
    """How many lines the innermost of `spans` that holds `line` takes from `line` on, where SwiftLint puts a
    function's row; 0 when none holds it."""
    inside = [last for first, last in spans if first <= line <= last]
    return min(inside) - line + 1 if inside else 0


def tree_smells(r: Reader, tree: Tree, lim: Limits, source: Optional[SwiftFile]) -> None:
    """Add the rows read from one file's tree, with SourceKit's tokens of it (`source`) to place an expression."""
    for (line, name), depth in nesting(tree).items():
        r.add(tree.rel, line or 1, "nesting", depth if depth > lim["nesting"][0] else None, name or "top level")
    for metric, lines in (("broad_catch", broad_catches(tree)), ("nested_ternary", nested_ternaries(tree, source)),
                          ("globals", list(globals_in(tree)))):
        for line in lines:
            r.add(tree.rel, line, metric, 1)


def swift_text(r: Reader, rels: List[str], lim: Limits) -> Dict[str, List[Tuple[int, int]]]:
    """Add the rows read from the trees of the Swift files `rels`: from swiftc's, the nesting, catches, ternaries and
    globals; from SourceKit's, the calls, parameters and comments. Code swiftc can't parse gives none. Give each
    file's function spans, which SwiftLint's rows of a function's length are given theirs from."""
    trees = parse(r.root, rels, r.notes)
    sources = {rel: open_text((r.root / rel).read_text(errors="replace")) for rel in rels}
    unread = [rel for rel, source in sources.items() if source is None]
    if unread:
        r.notes.append(SOURCEKIT_MISSING if library() is None else
                       f"sourcekitd didn't read {', '.join(unread)}, so its calls, parameters and comments aren't read")
    for tree in trees.values():
        tree_smells(r, tree, lim, sources.get(tree.rel))
    kept = len(r.rows)
    for rel, source in sources.items():
        if source is not None:
            test = [(line, "broad_test_asserts") for line in broad_asserts(source)] if TEST_FILE.search(rel) else []
            for line, metric in file_smells(source) + test:
                r.add(rel, line, metric, 1)
            for line, name in empty_tests(source) if TEST_FILE.search(rel) else []:
                r.add(rel, line, "broad_test_asserts", 1, nothing_key(name))
    for rel, line in commented_code(r.root, rels):
        r.add(rel, line, "commented_code", 1)
    r.rows[kept:] = [row for row in r.rows[kept:] if row.rel not in trees or not trees[row.rel].unread(row.line)]
    return {rel: function_spans(tree) for rel, tree in trees.items()}


def swift_unused(repo: Path, rels: List[str]) -> List[Tuple[str, int, str]]:
    """The private declarations nothing in their file names, in the Swift files `rels` of the real tree, as (rel,
    line, what): the real tree's, so that smells.py keeps those on the lines a change added, as for other dead code."""
    out = []
    for rel in rels:
        if Path(rel).suffix in SWIFT_EXTS and (repo / rel).is_file():
            source = open_text((repo / rel).read_text(errors="replace"))
            out += [(rel, line, what) for line, what in (unused_private(source) if source else [])]
    return out
