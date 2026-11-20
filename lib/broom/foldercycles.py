"""Imports that close a cycle between folders: the layers of a codebase going the wrong way. A file-level cycle is
one module importing back what imports it; a folder-level one is `auth` importing `providers` while `providers`
imports `auth`, however the files in between are arranged, which is where a layering that was meant to go one way
stops doing so.

Python's imports are read here (pycycles.py has the reader), and Rust's `use` statements (rustcycles.py). TS/JS's are read by dependency-cruiser, which resolves
tsconfig paths, index files and re-exports; it needs a TypeScript below 7 beside it to read .ts files at all, and says
nothing when it hasn't one (depcruise.py picks the one to run), so a changed file it didn't read is said so. An import counts where the change added it."""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Set, Tuple

from .gitutil import git, run
from .pycycles import ImportGraph
from .depcruise import pick
from .toolchain import JS_EXTS, find_up

Place = Tuple[str, int]  # a file, relative to the repo, and the line of an import in it
DEPCRUISE_EXCLUDE = r"(^|/)(node_modules|dist|build|out|coverage|\.next|\.git)(/|$)"
OUT_OF_TIME = "timeout:the time of this scan ran out before dependency-cruiser measured cycles between folders"


def folder_of(rel: str) -> str:
    """The folder of a POSIX relative path `rel`: its directory part, "" for a file at the root."""
    return posixpath.dirname(rel)


class Folders:
    """Which folders import which: `edges(folder)` is asked as the search goes, so only the folders a changed
    file's imports lead to are read."""

    def __init__(self, edges: Callable[[str], Iterable[str]]) -> None:
        self.edges = edges
        self.known: Dict[str, Set[str]] = {}

    def out(self, folder: str) -> Set[str]:
        """The folders that `folder` imports, not counting itself; read through edges() once and cached."""
        if folder not in self.known:
            self.known[folder] = set(self.edges(folder)) - {folder}
        return self.known[folder]

    def reaches(self, start: str, goal: str) -> bool:
        """Whether folder `goal` can be reached from folder `start` through the imports, for cycle checks."""
        seen: Set[str] = set()
        todo = [start]
        while todo:
            here = todo.pop()
            if here == goal:
                return True
            if here not in seen:
                seen.add(here)
                todo += self.out(here)
        return False


def python_folder_cycles(repo: Path, rels: List[str]) -> List[Place]:
    """The imports in the changed Python files that lead into another folder, which leads back to this one."""
    changed = [rel for rel in rels if rel.endswith(".py")]
    listing = git(["ls-files", "--cached", "--others", "--exclude-standard", "--", "*.py"], repo) if changed else None
    if not listing:
        return []
    files = [f for f in listing.splitlines() if f]
    return graph_folder_cycles(ImportGraph(repo, files), files, changed)


def graph_folder_cycles(graph: ImportGraph, files: List[str], changed: List[str],
                        folder: Callable[[str], str] = folder_of) -> List[Place]:
    """The imports in the `changed` files of `graph` that lead into another folder, which leads back to this one.
    `files` are all the files the graph holds; `folder` says which folder a file belongs to."""
    in_folder: Dict[str, List[str]] = {}
    for f in files:
        in_folder.setdefault(folder(f), []).append(f)
    folders = Folders(lambda d: {folder(t) for f in in_folder.get(d, []) for _, t in graph.edges(f)})
    return sorted({(rel, line) for rel in changed for line, target in graph.edges(rel)
                   if folder(target) != folder(rel) and folders.reaches(folder(target), folder(rel))})


def run_depcruise(root: Path, exe: str, timeout: float) -> Tuple[list, str]:
    """What dependency-cruiser read in `root`: its modules, and why not when it read none."""
    cmd = [exe, "--no-config", "--output-type", "json", "--exclude", DEPCRUISE_EXCLUDE]
    if (root / "tsconfig.json").is_file():
        cmd += ["--ts-config", "tsconfig.json"]
    rc, out, err = run(cmd + ["."], root, timeout=timeout)
    if rc is None:
        return [], "timeout"
    try:
        return json.loads(out)["modules"], ""
    except (ValueError, KeyError, TypeError):
        return [], f"failed: {(err or out).strip()[:120]}"


def import_line(text: str, specifiers: List[str]) -> int:
    """The line of the first import in `text` of one of `specifiers`, 0 when none is there."""
    for number, row in enumerate(text.splitlines(), 1):
        if any(re.search(r"""["'`]""" + re.escape(spec) + r"""["'`]""", row) for spec in specifiers):
            return number
    return 0


def package_cycles(repo: Path, prefix: str, group: List[str], modules: list, notes: List[str]) -> List[Place]:
    """The imports in the changed files `group` of one package that lead into a folder that leads back. `prefix`
    is the package's folder, which dependency-cruiser's paths leave out."""
    deps = {m["source"]: m.get("dependencies", []) for m in modules}
    imports = {src: [d["resolved"] for d in found if d.get("resolved") in deps and not d.get("couldNotResolve")]
               for src, found in deps.items()}
    in_folder: Dict[str, List[str]] = {}
    for source in imports:
        in_folder.setdefault(folder_of(source), []).append(source)
    folders = Folders(lambda d: {folder_of(t) for f in in_folder.get(d, []) for t in imports[f]})
    out: List[Place] = []
    for rel in group:
        source = rel[len(prefix):]
        if source not in imports:
            notes.append(f"dependency-cruiser didn't read {rel}: it needs a TypeScript below 7 beside it; broom doctor has the fix")
            continue
        text = (repo / rel).read_text(errors="replace")
        for target in imports[source]:
            if folder_of(target) != folder_of(source) and folders.reaches(folder_of(target), folder_of(source)):
                line = import_line(text, [d["module"] for d in deps[source] if d.get("resolved") == target])
                if line:
                    out.append((rel, line))
    return sorted(set(out))


def js_folder_cycles(repo: Path, rels: List[str], notes: List[str], timeout: Callable[[], float]) -> List[Place]:
    """The imports in the changed TS/JS files that lead into another folder, which leads back to this one. Each
    package (the nearest package.json) is read on its own, as imports between packages go through node_modules."""
    changed = [rel for rel in rels if Path(rel).suffix in JS_EXTS]
    exe = pick(repo) if changed else None  # without one, broom doctor says so
    if not exe:
        return []
    packages: Dict[Path, List[str]] = {}
    for rel in changed:
        found = find_up((repo / rel).parent, ["package.json"], repo)
        packages.setdefault(found.parent if found else repo, []).append(rel)
    out: List[Place] = []
    for root, group in packages.items():
        left = timeout()
        if not left:
            notes.append(OUT_OF_TIME)
            break
        modules, why = run_depcruise(root, exe, left)
        if why:
            notes.append(f"timeout:dependency-cruiser in {root}" if why == "timeout" else f"dependency-cruiser {why}")
            continue
        prefix = root.relative_to(repo).as_posix()
        out += package_cycles(repo, "" if prefix == "." else prefix + "/", group, modules, notes)
    return out
