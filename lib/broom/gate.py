"""What counts as a finding, the known-issue list, and the report Claude reads.

Lint findings count only on changed lines (git diff against HEAD; an untracked file counts whole), so a legacy
repo's old issues never land on Claude. Compile and type errors count anywhere: a changed signature breaks
callers in files nobody opened. A result Claude has seen and chosen not to fix is recorded as known and not
raised again.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .checks import Issue
from .common import DATA_ROOT, ChangedLines, load_json, save_json, short_hash

BASELINE = DATA_ROOT / "baseline.json"
MAX_SHOWN = 40

_lines: Dict[Path, List[str]] = {}


def line_text(f: Path, n: int) -> str:
    if f not in _lines:
        try:
            _lines[f] = f.read_text(errors="replace").splitlines()
        except OSError:
            _lines[f] = []
    rows = _lines[f]
    return rows[n - 1].strip() if 0 < n <= len(rows) else ""


def issue_key(i: Issue) -> str:
    # Keyed on the line's text, not its number, so a known issue stays known when lines above it move.
    return short_hash(f"{i.file}|{i.tool}|{i.rule}|{i.msg}|{line_text(i.file, i.line)}")


def verdict(issues: List[Issue]) -> str:
    return short_hash("".join(sorted(issue_key(i) for i in issues)))


def baseline_load() -> Set[str]:
    return set(load_json(BASELINE, {}))


def baseline_add(issues: List[Issue]) -> None:
    baseline_add_keys([issue_key(i) for i in issues])


def baseline_add_keys(keys: List[str]) -> None:
    data = load_json(BASELINE, {})
    now = time.time()
    data.update({k: now for k in keys})
    cutoff = now - 30 * 86400
    save_json(BASELINE, {k: t for k, t in data.items() if t >= cutoff})


def select(issues: List[Issue], files: Set[Path], known: Set[str]) -> List[Issue]:
    """The findings that count for `files`: see the module docstring."""
    changed = ChangedLines()
    seen: Set[Tuple[Path, int, int, str]] = set()
    out = []
    for i in issues:
        if not i.hard:
            if i.file not in files:
                continue
            lines = changed.get(i.file)
            if lines is not None and i.line not in lines:
                continue
        sig = (i.file, i.line, i.col, i.msg)
        if sig in seen or issue_key(i) in known:
            continue
        seen.add(sig)
        out.append(i)
    return out


def display(p: Path) -> str:
    home = str(Path.home())
    s = str(p)
    return "~" + s[len(home):] if s.startswith(home) else s


def rel(f: Path, root: Path) -> str:
    try:
        return str(f.relative_to(root))
    except ValueError:
        return display(f)


def note_text(n: str) -> str:
    return n.split(":", 1)[1] if n.startswith(("timeout:", "missing:")) else n


def render(head: str, issues: List[Issue], notes: List[str], files: Set[Path]) -> str:
    out = [head]
    groups: Dict[Tuple[str, Path], List[Issue]] = {}
    for i in issues:
        groups.setdefault((i.tool, i.root), []).append(i)
    shown = 0
    for (tool, root), items in groups.items():
        out.append(f"\n{tool} ({display(root)}):")
        for i in sorted(items, key=lambda x: (str(x.file), x.line, x.col)):
            if shown >= MAX_SHOWN:
                break
            where = f"{rel(i.file, root)}:{i.line}:{i.col}" if i.line else rel(i.file, root)
            tag = "" if i.file in files else "  [not in the changed files]"
            out.append(f"  {where}  {i.rule}  {i.msg}{tag}")
            shown += 1
    if len(issues) > shown:
        out.append(f"\n... and {len(issues) - shown} more")
    if notes:
        out.append("\nSkipped: " + "; ".join(note_text(n) for n in notes))
    return "\n".join(out)


def new_notes(state: Path, notes: List[str]) -> List[str]:
    """Notes not shown before in this session, so a missing tool is mentioned once, not every time."""
    seen = set(load_json(state, []))
    fresh = [n for n in notes if n not in seen]
    save_json(state, sorted(seen | set(fresh)))
    return fresh
