"""Swift's syntax tree from the compiler's own parser: `swiftc -frontend -dump-parse -dump-ast-format json` reads a
batch of files without building anything (decision 038), and each file's tree is a JSON object of nodes that carry a
`_kind`; a declaration or a statement carries its byte `range` too, an expression doesn't.

Code swiftc can't parse is not guessed at: the top-level declaration that holds an error is left out, with a note.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from .gitutil import run
from .reading import TOOL_TIMEOUT
from .swiftkit import Lines

MISSING = "missing:swiftc (it comes with Xcode or a Swift toolchain), so Swift's nesting, catches, ternaries, " \
          "globals and commented-out code aren't measured"
TREE_START = '{"_kind":"source_file","filename":'
BATCH = 200  # files to one swiftc: about 0.1 s and 15 MB of JSON per 50 files of 20 kB
# A line of swiftc's diagnostics, not of the source. With many files none is the script, so code at the top level
# of one is said to be not allowed there, but it parsed: the tree holds it.
ERROR = re.compile(r"^(.+?):(\d+):\d+: error: (?!(?:expressions|statements) are not allowed at the top level)", re.M)
# A copy of a node the parser keeps beside the original, or one it makes up: walked once, or not at all.
SKIP = {"processed_init", "desugared_loop", "compiler_version", "decl_context", "init_context"}
CLOSER = {"{": "}", "[": "]"}
JSON_TOKEN = re.compile(r'"":|"(?:\\.|[^"\\])*"|[{}\[\]]')  # a key "", a string or a bracket of swiftc's JSON


def repaired(text: str) -> str:
    """swiftc's JSON with each bracket it left open closed where an outer one closes, and a key "" in a list dropped.
    Swift 6.4's writer loses its place after an attributed type (`@Sendable () -> Void`): it leaves an object open,
    and writes the nodes after it as fields named "", in an object or in a list."""
    out, stack, last = [], [], 0
    for m in JSON_TOKEN.finditer(text):
        c, fix, end = m.group(), "", m.start()
        if c in CLOSER:
            stack.append(c)
        elif c == '"":' and stack and stack[-1] == "[":
            end = m.end()
        elif c in "}]":
            while stack and CLOSER[stack[-1]] != c:
                fix += CLOSER[stack.pop()]
            if stack:
                stack.pop()
        if fix or end > m.start():
            out += [text[last:m.start()], fix]
            last = end
    return "".join(out) + text[last:] + "".join(CLOSER[c] for c in reversed(stack))


def keep_unnamed(pairs: List[Tuple[str, object]]) -> dict:
    """A JSON object from `pairs`, the nodes under a repeated "" key kept as a list."""
    out: dict = {}
    for key, value in pairs:
        if key:
            out[key] = value
        else:
            out.setdefault("", []).append(value)
    return out


def decode(text: str) -> Optional[dict]:
    """One file's tree from swiftc's JSON, repaired when it doesn't decode; None when it can't be read."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return json.loads(repaired(text), object_pairs_hook=keep_unnamed)
    except ValueError:
        return None


def children(node: dict) -> Iterator[Tuple[str, dict]]:
    """The nodes right under `node`, each with the key it sits under."""
    for key, value in node.items():
        if key in SKIP:
            continue
        if isinstance(value, dict):
            yield key, value
        elif isinstance(value, list):
            yield from ((key, v) for v in value if isinstance(v, dict))


def walk(node: dict) -> Iterator[dict]:
    """`node` and every node under it."""
    yield node
    for _, child in children(node):
        yield from walk(child)


def kind(node: dict) -> str:
    """What a node is: `func_decl`, `if_stmt`, `call_expr` ..."""
    return str(node.get("_kind", ""))


def name_of(node: dict) -> str:
    """The base name a declaration or a reference carries, "" when none."""
    name = node.get("name")
    if isinstance(name, dict):
        name = (name.get("base_name") or {}).get("name")
    return name if isinstance(name, str) else ""


@dataclass
class Tree(Lines):
    """The tree of one Swift file: `rel` its path, `items` its top-level nodes, `data` its bytes, and `bad` the line
    spans of the top-level declarations swiftc couldn't parse, which are left out of `items`."""
    rel: str
    items: List[dict]
    data: bytes
    bad: List[Tuple[int, int]] = field(default_factory=list)
    starts: List[int] = field(default_factory=list)

    def lines(self, node: dict) -> Optional[Tuple[int, int]]:
        """The first and last line of a node that carries a range; None for one that doesn't."""
        span = node.get("range")
        if not isinstance(span, dict) or "start" not in span:
            return None
        return self.line(int(span["start"])), self.line(int(span.get("end", span["start"])))

    def unread(self, line: int) -> bool:
        """Whether `line` lies in code swiftc couldn't parse."""
        return any(a <= line <= b for a, b in self.bad)


def split_trees(out: str) -> Iterator[dict]:
    """Each file's tree in the output of one swiftc run over many files."""
    starts = [m.start() for m in re.finditer(re.escape(TREE_START), out)]
    for a, b in zip(starts, starts[1:] + [len(out)]):
        tree = decode(out[a:b])
        if tree is not None:
            yield tree


def tree_of(root: Path, raw: dict, errors: List[int], notes: List[str]) -> Tuple[str, Tree]:
    """The Tree of swiftc's `raw` tree for a file under `root`, the top-level nodes holding an error line in `errors`
    left out with a note."""
    rel = str(raw.get("filename", ""))
    tree = Tree(rel, [], (root / rel).read_bytes())
    for item in raw.get("items") or []:
        span = tree.lines(item)
        hit = [n for n in errors if span and span[0] <= n <= span[1]]
        if hit:
            tree.bad.append(span)
            notes.append(f"swiftc can't parse {rel}:{hit[0]}, so broom reads no smell in lines {span[0]}-{span[1]}")
        else:
            tree.items.append(item)
    tree.bad += [(n, n) for n in errors if not tree.unread(n)]
    return rel, tree


def parse(root: Path, rels: List[str], notes: List[str], timeout: float = TOOL_TIMEOUT) -> Dict[str, Tree]:
    """The tree of each Swift file `rels` under `root`, read by swiftc in batches; a missing swiftc or a timeout gives
    no trees and a note."""
    swiftc = shutil.which("swiftc")
    if not swiftc:
        notes.append(MISSING)
        return {}
    trees: Dict[str, Tree] = {}
    for n in range(0, len(rels), BATCH):
        batch = rels[n:n + BATCH]
        args = [arg for rel in batch for arg in ("-primary-file", rel)]
        rc, out, err = run([swiftc, "-frontend", "-dump-parse", "-dump-ast-format", "json", *args], root,
                           timeout=timeout)
        if rc is None:
            notes.append("timeout:swiftc reading Swift's syntax tree")
            break
        errors: Dict[str, List[int]] = {}
        for m in ERROR.finditer(err):
            errors.setdefault(m[1], []).append(int(m[2]))
        trees.update(tree_of(root, raw, errors.get(str(raw.get("filename")), []), notes) for raw in split_trees(out))
        notes += [f"swiftc's tree of {rel} couldn't be read, so broom reads no smell in it from the tree"
                  for rel in batch if rel not in trees]
    return trees
