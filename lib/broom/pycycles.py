"""Python imports that close a cycle: no tool does this, so broom reads the imports itself, from the syntax tree.

Only imports at module level count. One inside a function, or under `if TYPE_CHECKING:`, is how code breaks a cycle
on purpose. An import counts when what it imports leads back to the file it is in."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .gitutil import git

Edge = Tuple[int, str]  # the line of an import, and the file it imports


def module_names(files: List[str]) -> Dict[str, Optional[str]]:
    """Every dotted suffix of a module's path, to its file; None where two files share it. `src/pkg/a.py` is
    `a`, `pkg.a` and `src.pkg.a`, whichever of them the code imports it by."""
    names: Dict[str, Optional[str]] = {}
    for rel in files:
        parts = rel[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        for i in range(len(parts)):
            name = ".".join(parts[i:])
            names[name] = None if names.get(name, rel) != rel else rel
    return names


def is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def module_level_imports(body: List[ast.stmt]) -> Iterator[ast.stmt]:
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, ast.If) and not is_type_checking(node.test):
            yield from module_level_imports(node.body + node.orelse)
        elif isinstance(node, ast.Try):
            yield from module_level_imports(node.body + node.orelse + node.finalbody
                                            + [s for h in node.handlers for s in h.body])
        elif isinstance(node, ast.With):
            yield from module_level_imports(node.body)


def names_imported(node: ast.stmt, rel: str) -> List[str]:
    """The dotted names an import may mean: the module, and each name it takes, which may be a module too."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    assert isinstance(node, ast.ImportFrom)
    package = rel.split("/")[:-1]
    base = package[:len(package) - (node.level - 1)] if node.level else []
    module = ".".join(base + ([node.module] if node.module else []))
    return [module, *(f"{module}.{a.name}" if module else a.name for a in node.names)]


class ImportGraph:
    """The module-level imports of the repo's Python files, read as they are asked for."""

    def __init__(self, repo: Path, files: List[str]) -> None:
        self.repo = repo
        self.names = module_names(files)
        self._edges: Dict[str, List[Edge]] = {}

    def edges(self, rel: str) -> List[Edge]:
        if rel not in self._edges:
            self._edges[rel] = self._read(rel)
        return self._edges[rel]

    def _read(self, rel: str) -> List[Edge]:
        try:
            tree = ast.parse((self.repo / rel).read_text(errors="replace"))
        except (SyntaxError, ValueError, OSError):
            return []
        out = []
        for node in module_level_imports(tree.body):
            targets = {self.names.get(n) for n in names_imported(node, rel)} - {None, rel}
            out += [(node.lineno, t) for t in sorted(t for t in targets if t)]
        return out

    def reaches(self, start: str, goal: str) -> bool:
        seen: Set[str] = set()
        todo = [start]
        while todo:
            here = todo.pop()
            if here == goal:
                return True
            if here not in seen:
                seen.add(here)
                todo += [t for _, t in self.edges(here)]
        return False


def import_cycles(repo: Path, rels: List[str]) -> List[Tuple[str, int]]:
    """(file, line) of each module-level import in the Python files `rels` that leads back to the file."""
    changed = [rel for rel in rels if rel.endswith(".py")]
    listing = git(["ls-files", "--cached", "--others", "--exclude-standard", "--", "*.py"], repo) if changed else None
    if not listing:
        return []
    graph = ImportGraph(repo, [f for f in listing.splitlines() if f])
    return [(rel, line) for rel in changed for line, target in graph.edges(rel) if graph.reaches(target, rel)]
