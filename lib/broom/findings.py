"""What a linter or a type check reports, and what the parsers of their output share."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class Issue:
    tool: str
    root: Path  # where the check ran, for grouping the report
    file: Path
    line: int
    col: int
    rule: str
    msg: str
    hard: bool = False  # compile/type error: counts outside the changed lines and files
    severe: bool = False  # a code smell past its hard limit: like a hard error, it never passes on a retry alone


Findings = Tuple[List[Issue], List[str]]


def resolve_in(root: Path, name: str, *fallbacks: Optional[Path]) -> Path:
    p = Path(name)
    if p.is_absolute():
        return p.resolve()
    for base in (root, *fallbacks):
        if base and (base / p).exists():
            return (base / p).resolve()
    return (root / p).resolve()


def targets(files: List[Path], whole: bool) -> List[str]:
    """What to hand a linter: the files, or its whole project (it runs from the project directory)."""
    return ["."] if whole else [str(f) for f in files]


def failure(out: str, err: str) -> str:
    """The first lines explaining why a tool failed; some tools print config errors on stdout."""
    rows = [r.strip(" |x\t") for r in (err.strip() or out.strip()).splitlines()]
    return " / ".join(r for r in rows if r)[:200] or "no output"
