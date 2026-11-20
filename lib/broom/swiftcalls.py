"""Swift smells read from SourceKit's structure and tokens (swiftkit): a debug print, an unlabeled Bool parameter, a
test that any error at all is thrown, a skipped test, a test case, and a private name nothing in its file uses. Each
is a node of the parser's structure, a call, a parameter or a declaration, and a token's text is only ever compared
whole, so a string or a comment that looks like one is never taken for it.
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Tuple

from .swiftkit import Node, SwiftFile

DEBUG_CALLS = {"print", "debugPrint", "NSLog", "dump"}  # the free functions; `printer.print(` is a method
CONDITIONAL_SKIPS = {"XCTSkipIf", "XCTSkipUnless"}
ANY_ERROR = {"any", "Error", "self"}  # the tokens of `Error.self` and `(any Error).self`
CONDITIONS = {"stmt.if", "stmt.guard", "stmt.switch"}
# Used from outside the source's sight: by the Objective-C runtime, Interface Builder, Core Data, or a superclass.
KEPT = {"objc", "objc.name", "nsmanaged", "override", "dynamic", "ibaction", "iboutlet", "ibinspectable",
        "ibdesignable", "ibsegueaction"}
IMPLICIT = {"CodingKeys", "init", "deinit", "subscript"}  # named by the compiler, never by the code
PRIVATE = {"private", "fileprivate"}
REFERENCE = {"identifier", "typeidentifier"}  # the kinds of token that name something


def attributes(n: Node) -> List[str]:
    """The attributes of a declaration, by the last parts of their kinds: `private`, `objc`, `_custom` ..."""
    return [str(a.get("key.attribute", "")).replace("source.decl.attribute.", "") for a in n.raw.get("key.attributes")
            or []]


def labels(n: Node) -> List[str]:
    """The argument labels in a function's full name: `f(_:verbose:)` gives `_` and `verbose`."""
    inside = n.name.partition("(")[2].rstrip(")")
    return [part for part in inside.split(":")[:-1]]


def walk_with_parents(n: Node, parents: Tuple[Node, ...] = ()) -> Iterator[Tuple[Node, Tuple[Node, ...]]]:
    """Every node under `n` with the nodes above it, outermost first."""
    for child in n.children:
        yield child, parents
        yield from walk_with_parents(child, (*parents, child))


def debug_calls(f: SwiftFile) -> Iterator[int]:
    """The lines of calls of `print`, `debugPrint`, `NSLog` or `dump`, the free functions, `Swift.` before or not."""
    for n in f.root.walk():
        if n.kind == "expr.call" and n.name.replace("Swift.", "", 1) in DEBUG_CALLS:
            yield f.line(n.offset)


def bool_params(f: SwiftFile) -> Iterator[int]:
    """The lines of a function's parameters typed `Bool` with no argument label: `f(true)` says nothing at the call."""
    for n in f.root.walk():
        if not n.kind.startswith("decl.function"):
            continue
        params = [c for c in n.children if c.kind == "decl.var.parameter"]
        for label, param in zip(labels(n), params):
            if label == "_" and param.raw.get("key.typename") == "Bool":
                yield f.line(param.offset)


def macro_before(f: SwiftFile, n: Node) -> Optional[str]:
    """The name of the macro whose arguments `n` starts, as `expect` in `#expect(throws: …)`; None when no
    identifier token comes before it."""
    before = [t for t in f.tokens if t.offset < n.offset]
    return before[-1].text if before and before[-1].kind == "identifier" else None


def broad_asserts(f: SwiftFile) -> Iterator[int]:
    """The lines of checks that some error is thrown, any error: `XCTAssertThrowsError` with no handler to look at
    it, and swift-testing's `#expect(throws: Error.self)` or `(any Error).self`, `#require` too."""
    for n, parents in walk_with_parents(f.root):
        if n.kind == "expr.call" and n.name == "XCTAssertThrowsError":
            args = [c for c in n.children if c.kind == "expr.argument"]
            if not any(a.name == "errorHandler" or any(c.kind == "expr.closure" for c in a.children) for a in args):
                yield f.line(n.offset)
        elif n.kind == "expr.argument" and n.name == "throws" and (not parents or parents[-1].kind != "expr.call"):
            words = [t.text for t in f.within(n)][1:]
            if macro_before(f, n) in ("expect", "require") and "Error" in words and set(words) <= ANY_ERROR:
                yield f.line(n.offset)


def file_smells(f: SwiftFile) -> List[Tuple[int, str]]:
    """The (line, smell) of the debug prints and the unlabeled Bool parameters in one file."""
    return [(line, "debug_output") for line in debug_calls(f)] + [(line, "bool_params") for line in bool_params(f)]


def skips(f: SwiftFile) -> Iterator[Tuple[int, bool]]:
    """Each skipped or disabled test, as (line, whether a condition decides it): `XCTSkip` thrown, and swift-testing's
    `.disabled` trait. `XCTSkipIf`, `XCTSkipUnless`, `.disabled(if:)` and a skip inside an `if` or a `guard` are
    conditional."""
    for n, parents in walk_with_parents(f.root):
        if n.kind != "expr.call":
            continue
        if n.name.startswith("XCTSkip"):
            conditional = n.name in CONDITIONAL_SKIPS or any(p.kind in CONDITIONS for p in parents)
            yield f.line(n.offset), conditional
        elif n.name == ".disabled":
            yield f.line(n.offset), any(c.name == "if" for c in n.children)


def test_cases(f: SwiftFile) -> int:
    """How many test cases `f` declares: methods named `test…` (XCTest) and functions marked `@Test`."""
    count = 0
    for n in f.root.walk():
        if n.kind.startswith("decl.function"):
            marked = any(t.text == "Test" for a in n.raw.get("key.attributes") or []
                         for t in f.tokens if t.offset == int(a.get("key.offset", -1)) + 1)
            count += marked or n.name.startswith("test")
    return count


def what_is(f: SwiftFile, n: Node) -> str:
    """A declaration as `func helper` or `let lonely`: the keyword it starts with and its name."""
    keyword = next((t.text for t in f.tokens if t.offset == n.offset), n.kind.rsplit(".", 1)[-1])
    return f"{keyword} {n.name.partition('(')[0]}"


def unused_private(f: SwiftFile) -> List[Tuple[int, str]]:
    """The private and fileprivate declarations whose name no other token of the file names, as (line, what):
    nothing outside the file can use them. A name in a comment or a string is no use of it."""
    names = {}
    for t in f.tokens:
        if t.kind in REFERENCE:
            names.setdefault(t.text.strip("`"), []).append(t.offset)
    out = []
    for n in f.root.walk():
        attrs = set(attributes(n))
        name = n.name.partition("(")[0].strip("`")
        if not n.kind.startswith("decl.") or not attrs & PRIVATE or {a.lower() for a in attrs} & KEPT:
            continue
        if name in IMPLICIT or not name[:1].isidentifier():
            continue
        own = int(n.raw.get("key.nameoffset", -1))
        if not [offset for offset in names.get(name, []) if offset != own]:
            out.append((f.line(n.offset), what_is(f, n)))
    return out
