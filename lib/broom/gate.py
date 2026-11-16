"""What counts as a finding, the known-issue list, and the report Claude reads.

Lint findings count only on changed lines (git diff against a base revision; a new file counts whole), so a
legacy repo's old issues never land on Claude. Compile and type errors count anywhere: a changed signature
breaks callers in files nobody opened. A result Claude has seen and chosen not to fix is recorded as known and
not raised again; `broom known` lists and clears those.
"""

from __future__ import annotations

import os
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .findings import Issue
from .config import excluded
from .gitutil import ChangedLines
from .state import DATA_ROOT, load_json, short_hash, update_json

BASELINE = DATA_ROOT / "baseline.json"
COMMITS = DATA_ROOT / "commits.json"  # per repo: the last blocked commit's verdict, denials and pending issues
BASELINE_DAYS = 30
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


def issue_entry(i: Issue) -> Dict[str, object]:
    return {"t": time.time(), "file": str(i.file), "line": i.line, "tool": i.tool, "rule": i.rule, "msg": i.msg}


def verdict(issues: List[Issue]) -> str:
    return short_hash("".join(sorted(issue_key(i) for i in issues)))


# ---------------------------------------------------------------- known issues


def baseline_entries(raw: dict) -> Dict[str, dict]:
    # 0.2 stored a bare timestamp per key.
    return {k: (v if isinstance(v, dict) else {"t": v}) for k, v in raw.items()}


def baseline_load() -> Dict[str, dict]:
    return baseline_entries(load_json(BASELINE, {}))


def baseline_keys() -> Set[str]:
    return set(baseline_load())


def baseline_add(issues: List[Issue]) -> None:
    baseline_add_entries({issue_key(i): issue_entry(i) for i in issues})


def baseline_add_entries(entries: Dict[str, dict]) -> None:
    cutoff = time.time() - BASELINE_DAYS * 86400

    def add(raw: dict) -> dict:
        data = baseline_entries(raw)
        data.update(entries)
        return {k: v for k, v in data.items() if v.get("t", 0) >= cutoff}

    update_json(BASELINE, {}, add)


def save_commits(state: dict, repos: Iterable[Path]) -> None:
    """Write this run's repos' entries of the last-blocked-commit record back, and leave the other repos' as they
    are on disk: another hook may have changed them since this one read the file."""
    keys = {str(r) for r in repos}

    def put(data: dict) -> None:
        for key in keys:
            if key in state:
                data[key] = state[key]
            else:
                data.pop(key, None)

    update_json(COMMITS, {}, put)


def accept_allowed() -> bool:
    """Whether `broom known --accept` works here: `BROOM_NO_ACCEPT` (set to anything but 0) turns it off, for
    agents that must fix what they break instead of accepting it."""
    return os.environ.get("BROOM_NO_ACCEPT", "") in ("", "0")


def accept_blocked(repo: Path, why: str) -> int:
    """Record the issues of the last commit broom blocked in `repo` as known, with the reason. Returns how many."""
    state = load_json(COMMITS, {})
    pending = (state.get(str(repo)) or {}).get("pending") or {}
    if pending:
        now = time.time()
        baseline_add_entries({k: {**v, "t": now, "why": why} for k, v in pending.items()})
        state.pop(str(repo), None)
        save_commits(state, [repo])
    return len(pending)


def baseline_under(roots: List[Path]) -> Dict[str, dict]:
    """Known issues in files under any of `roots`."""
    out = {}
    for k, v in baseline_load().items():
        f = Path(str(v.get("file", "")))
        if any(f == r or r in f.parents for r in roots):
            out[k] = v
    return out


def baseline_remove(keys: List[str]) -> None:
    def drop(raw: dict) -> dict:
        data = baseline_entries(raw)
        for k in keys:
            data.pop(k, None)
        return data

    update_json(BASELINE, {}, drop)


# ---------------------------------------------------------------- selection and report


def select(issues: List[Issue], files: Set[Path], known: Set[str], changed: Optional[ChangedLines] = None,
           *, whole: bool = False) -> List[Issue]:
    """The findings that count: see the module docstring. `whole` counts every line of every file. Files the
    repo's .broom.json excludes never count."""
    changed = changed or ChangedLines()
    seen: Set[Tuple[Path, int, int, str]] = set()
    out = []
    for i in issues:
        if not (i.hard or whole):
            if i.file not in files:
                continue
            lines = changed.get(i.file)
            if lines is not None and i.line not in lines:
                continue
        sig = (i.file, i.line, i.col, i.msg)
        if sig in seen or issue_key(i) in known or excluded(i.file):
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


def setup_hint(notes: List[str]) -> str:
    missing = [n for n in notes if n.startswith("missing:")]
    return "Some checks couldn't run because tools are missing: offer the user /broom:setup." if missing else ""


def render(head: str, issues: List[Issue], notes: List[str], files: Set[Path]) -> str:
    out = [head]
    if len(issues) > MAX_SHOWN:
        top = Counter(f"{i.tool} {i.rule}" for i in issues).most_common(10)
        out.append("\nMost frequent: " + ", ".join(f"{rule} ×{n}" for rule, n in top))
    groups: Dict[Tuple[str, Path], List[Issue]] = {}
    for i in issues:
        groups.setdefault((i.tool, i.root), []).append(i)
    shown = 0
    for (tool, root), items in groups.items():
        if shown >= MAX_SHOWN:
            break
        out.append(f"\n{tool} ({display(root)}):")
        for i in sorted(items, key=lambda x: (str(x.file), x.line, x.col)):
            if shown >= MAX_SHOWN:
                break
            where = f"{rel(i.file, root)}:{i.line}:{i.col}" if i.line else rel(i.file, root)
            tag = "" if i.file in files or not files else "  [not in the changed files]"
            out.append(f"  {where}  {i.rule}  {i.msg}{tag}")
            shown += 1
    if len(issues) > shown:
        out.append(f"\n... and {len(issues) - shown} more")
    if notes:
        out.append("\nSkipped: " + "; ".join(note_text(n) for n in notes))
        hint = setup_hint(notes)
        if hint:
            out.append(hint)
    return "\n".join(out)


def new_notes(state: Path, notes: List[str]) -> List[str]:
    """Notes not shown before in this session, so a missing tool is mentioned once, not every time."""
    fresh: List[str] = []

    def add(seen_before: list) -> list:
        fresh[:] = [n for n in notes if n not in set(seen_before)]
        return sorted(set(seen_before) | set(fresh))

    update_json(state, [], add)
    return fresh
