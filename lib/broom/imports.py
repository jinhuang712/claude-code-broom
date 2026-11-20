"""A file's imports, read from its syntax tree (decision 038), never from its text: an `import` in a string or a
comment is none. Python's come from the standard library's `ast`, Swift's from SourceKit's tokens, and Go's and
TS/JS's from ast-grep's rules `*-imports.yml` under `defaults/sg/rules/`.

`import_lines` tells a longer file from longer imports (smells.drop_import_growth); `import_sources` gives the line of
each module a TS/JS file names in an import, for the import dependency-cruiser named (foldercycles.py).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .reading import TOOL_TIMEOUT
from .swiftkit import import_lines as swift_import_lines
from .syntax import Rules, matches, text_matches
from .toolchain import GO_EXTS, JS_EXTS, PY_EXTS, SWIFT_EXTS

DECL_RULES = Rules(only="-import-decl$")
SOURCE_RULES = Rules(only="-import-source$")
SG_EXTS = GO_EXTS | JS_EXTS


def python_import_lines(text: str) -> int:
    """How many lines the `import` and `from … import` statements of the Python source `text` span; 0 for source
    that doesn't parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return 0
    lines: Set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return len(lines)


def import_lines(texts: Dict[str, str], notes: List[str]) -> Dict[str, int]:
    """Per file of `texts` (a path to its text), how many lines its import declarations span: Python's and Swift's
    read here, Go's and TS/JS's by one run of ast-grep. A file of another language, or one whose tree couldn't be
    read, has none."""
    out = {rel: 0 for rel in texts}
    for rel, text in texts.items():
        ext = Path(rel).suffix
        if ext in PY_EXTS:
            out[rel] = python_import_lines(text)
        elif ext in SWIFT_EXTS:
            out[rel] = swift_import_lines(text)
    sg = {rel: text for rel, text in texts.items() if Path(rel).suffix in SG_EXTS}
    spans: Dict[str, Set[int]] = {}
    for m in text_matches(sg, notes, TOOL_TIMEOUT, DECL_RULES):
        spans.setdefault(m.file, set()).update(range(m.line, m.end + 1))
    out.update((rel, len(lines)) for rel, lines in spans.items() if rel in out)
    return out


def import_sources(root: Path, rels: List[str], notes: List[str]) -> Dict[str, List[Tuple[int, str]]]:
    """Per TS/JS file of `rels` under `root`, each module it names in an `import`, an `export … from`, a `require()`
    or an `import()`, as (line, the string's content), in line order."""
    out: Dict[str, List[Tuple[int, str]]] = {rel: [] for rel in rels}
    for m in matches(root, rels, notes, TOOL_TIMEOUT, SOURCE_RULES):
        literal = m.caught.get("TEXT", "")
        out.setdefault(m.file, []).append((m.line, literal[1:-1]))  # the string without its quotes or backticks
    for found in out.values():
        found.sort()
    return out
