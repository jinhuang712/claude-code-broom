"""Rust `use` statements that close a cycle, between files or between folders. The compiler allows a cycle of
modules, so no tool reports one; broom reads the `use` statements itself.

A crate's modules are its files under `src/`: `src/a/b.rs` and `src/a/b/mod.rs` are `crate::a::b`, and `src/lib.rs`
(else `src/main.rs`) is the crate root. A path is read from the module it is written in (`crate::`, `super::`,
`self::`, or a bare name of a module beside it), and leads to the deepest module it names that is a file: an item of
a module is in that module's file. A path to another crate leads nowhere. `use` in test code doesn't count, nor do
`mod` declarations, which every parent has of its children.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .foldercycles import Place, folder_of, graph_folder_cycles
from .gitutil import git
from .pycycles import Edge, ImportGraph
from .rustmeasure import clean, test_start

USE = re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?\s+)?use\s+([^;]*);", re.M)
Module = Tuple[str, Tuple[str, ...]]  # a crate's `src/` folder and a module's path in it


def module_of(rel: str) -> Optional[Module]:
    """The crate source folder and module path of the file `rel`; None for a file outside any `src/` or under
    `src/bin/`, which holds crates of its own."""
    m = re.match(r"((?:.*/)?src/)(.+)\.rs$", rel)
    if not m or m[2].startswith("bin/"):
        return None
    parts = tuple(m[2].split("/"))
    if parts[-1] == "mod":
        parts = parts[:-1]
    return m[1], () if parts in (("lib",), ("main",)) else parts


def split_top(group: str) -> List[str]:
    """The parts of a `{...}` group's inside, split at its own commas, not those of a group inside it."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(group):
        depth += {"{": 1, "}": -1}.get(ch, 0)
        if ch == "," and not depth:
            parts.append(group[start:i])
            start = i + 1
    return [p for p in parts + [group[start:]] if p]


def use_paths(tree: str) -> List[List[str]]:
    """Each path a use tree names: `crate::{a::X, b::{self, Y}}` is crate/a/X, crate/b and crate/b/Y."""
    tree = re.sub(r"\s", "", re.sub(r"\s+as\s+\w+", "", tree))
    at = tree.find("{")
    if at < 0:
        return [[p for p in tree.split("::") if p and p != "self"]]
    head = [p for p in tree[:at].split("::") if p and p != "self"]
    return [head + tail for part in split_top(tree[at + 1:tree.rfind("}")]) for tail in use_paths(part)]


def absolute(here: Tuple[str, ...], path: List[str]) -> List[str]:
    """`path`, written in module `here`, as a path from the crate root."""
    if path[:1] == ["crate"]:
        return path[1:]
    base = list(here)
    while path[:1] == ["super"]:
        base, path = base[:-1], path[1:]
    return base + path


class RustGraph(ImportGraph):
    """The `use` statements of a repo's Rust files, read as they are asked for."""

    def __init__(self, repo: Path, files: List[str]) -> None:
        super().__init__(repo, [])
        self.modules: Dict[Module, str] = {}
        for rel in sorted(files):  # lib.rs before main.rs: the crate root of a crate that has both
            key = module_of(rel)
            if key:
                self.modules.setdefault(key, rel)

    def target(self, src: str, path: List[str]) -> Optional[str]:
        """The file of the deepest module that `path` (from the crate root) names, or None when it names none."""
        for k in range(len(path), -1, -1):
            found = self.modules.get((src, tuple(path[:k])))
            if found:
                return found
        return None

    def resolve(self, key: Module, path: List[str]) -> Optional[str]:
        """The file a path written in module `key` leads to. A bare first name (or one after `self::`) is a module
        beside it, else another crate's."""
        src, here = key
        if path[:1] not in (["crate"], ["super"]) and (src, (*here, *path[:1])) not in self.modules:
            return None
        return self.target(src, absolute(here, path))

    def _read(self, rel: str) -> List[Edge]:
        key = module_of(rel)
        try:
            rows = clean((self.repo / rel).read_text(errors="replace"))[0] if key else []
        except OSError:
            return []
        text = "\n".join(rows[:test_start(rel, rows)])
        out = set()
        for m in USE.finditer(text):
            found = {self.resolve(key, path) for path in use_paths(m[1])} - {None, rel}
            out |= {(text.count("\n", 0, m.start()) + 1, f) for f in found if f}
        return sorted(out)


def rust_graph(repo: Path, rels: List[str]) -> Tuple[Optional[RustGraph], List[str], List[str]]:
    """The graph of the repo's Rust files, all of them, and the changed ones among `rels`; no graph when none is."""
    changed = [rel for rel in rels if rel.endswith(".rs")]
    listing = git(["ls-files", "--cached", "--others", "--exclude-standard", "--", "*.rs"], repo) if changed else None
    if not listing:
        return None, [], []
    files = [f for f in listing.splitlines() if f]
    return RustGraph(repo, files), files, changed


def rust_import_cycles(repo: Path, rels: List[str]) -> List[Place]:
    """(file, line) of each `use` in the Rust files `rels` that leads back to the file."""
    graph, _, changed = rust_graph(repo, rels)
    if not graph:
        return []
    return [(rel, line) for rel in changed for line, target in graph.edges(rel) if graph.reaches(target, rel)]


def rust_folder_cycles(repo: Path, rels: List[str]) -> List[Place]:
    """The `use` statements in the Rust files `rels` that lead into another folder, which leads back to this one.
    A module's folder is the one its children live in: `src/a.rs` belongs with `src/a/` when there is one, as
    `src/a/mod.rs` does, so a child that uses its parent stays inside one folder."""
    graph, files, changed = rust_graph(repo, rels)
    if not graph:
        return []
    dirs = {folder_of(f) for f in files}

    def folder(rel: str) -> str:
        return rel[:-3] if rel[:-3] in dirs else posixpath.dirname(rel)

    return graph_folder_cycles(graph, files, changed, folder)
