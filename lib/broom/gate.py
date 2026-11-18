"""What counts as a finding, the known-issue list, and the report Claude reads.

Lint findings count only on changed lines (git diff against a base revision; a new file counts whole), so a
legacy repo's old issues never land on Claude. Compile and type errors count anywhere: a changed signature
breaks callers in files nobody opened. A finding Claude accepts with a reason (`broom known --accept`) is recorded
as known and not raised again; `broom known` lists and clears those.
"""

from __future__ import annotations

import os
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from . import ledger
from .findings import Issue
from .config import OPTIONAL_NOTE, TESTS_TOOL, excluded
from .fixes import how_to_fix
from .gitutil import ChangedLines
from .state import DATA_ROOT, load_json, say, short_hash, update_json

BASELINE = DATA_ROOT / "baseline.json"
COMMITS = DATA_ROOT / "commits.json"  # per repo: what the last commit or turn end blocked, by which hook
STOPS = ("stop", "subagent-stop")  # the hooks of a turn's end, as the ledger and commits.json name them
BASELINE_DAYS = 30
MAX_SHOWN = 40
MAX_CHARS = 9000  # what a block message holds at most: findings give way to the rest of it
MORE_ROOM = 40  # for the "... and N more" line

_lines: Dict[Path, List[str]] = {}


def line_text(f: Path, n: int) -> str:
    """The stripped text of line `n` (1-based) in `f`, cached per file; "" when the line or the file is missing."""
    if f not in _lines:
        try:
            _lines[f] = f.read_text(errors="replace").splitlines()
        except OSError:
            _lines[f] = []
    rows = _lines[f]
    return rows[n - 1].strip() if 0 < n <= len(rows) else ""


def issue_key(i: Issue) -> str:
    """A short id for a finding: its file, tool, rule and message plus the text of its line, not its number."""
    # Keyed on the line's text, not its number, so a known issue stays known when lines above it move.
    return short_hash(f"{i.file}|{i.tool}|{i.rule}|{i.msg}|{line_text(i.file, i.line)}")


def issue_entry(i: Issue) -> Dict[str, object]:
    """The finding as a dict stamped with the time, for the baseline and commit record; `grown_from` if set."""
    entry: Dict[str, object] = {"t": time.time(), "file": str(i.file), "line": i.line, "tool": i.tool,
                                "rule": i.rule, "msg": i.msg}
    if i.grown_from is not None:
        entry["grown_from"] = i.grown_from  # `broom known --accept` leaves it out
    return entry


# ---------------------------------------------------------------- known issues


def baseline_entries(raw: dict) -> Dict[str, dict]:
    """The baseline as a dict of key to entry; the bare timestamp of version 0.2 becomes {"t": timestamp}."""
    # 0.2 stored a bare timestamp per key.
    return {k: (v if isinstance(v, dict) else {"t": v}) for k, v in raw.items()}


def baseline_load() -> Dict[str, dict]:
    """The known-issue baseline from disk, keyed by issue key; empty when there is none."""
    return baseline_entries(load_json(BASELINE, {}))


def baseline_keys() -> Set[str]:
    """The keys of the baseline's known issues, for telling which findings are already known."""
    return set(baseline_load())


def baseline_add_entries(entries: Dict[str, dict]) -> None:
    """Add `entries` to the baseline on disk, dropping entries older than BASELINE_DAYS; takes the file's lock."""
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


def open_findings(record: dict) -> Dict[str, dict]:
    """The findings a repo's last-blocked record holds that no check has ended: the last block's (`pending`) and the
    commit blocks' that a turn-end block replaced as the last (`earlier`). Only `pending` can be accepted; both can be
    fixed."""
    return {**(record.get("earlier") or {}), **(record.get("pending") or {})}


def commit_blocks(record: object) -> Dict[str, dict]:
    """What commits blocked in a repo and no check has ended, from the repo's last-blocked `record`: its `earlier`, and
    its `pending` unless a turn's end blocked last. A turn-end block is no part of it: the turn's gate.json holds it,
    and the turn's own end writes its outcome."""
    if not isinstance(record, dict):
        return {}
    last = {} if record.get("where") in STOPS else record.get("pending") or {}
    return {**(record.get("earlier") or {}), **last}


def kept_blocks(record: object, known: Set[str], settled: Iterable[str]) -> Dict[str, dict]:
    """What commits blocked before and a check leaves open, for the repo's `earlier`: `commit_blocks` less what the check
    `settled` (found again, which the new block holds, or ended), what was accepted since (`known`) and what is in a file
    that is gone. A finding stays until it is fixed, accepted or its file is gone, so the record never grows past
    what is open."""
    done = set(settled)
    return {k: e for k, e in commit_blocks(record).items()
            if k not in done and k not in known and Path(str(e.get("file") or "")).is_file()}


def last_block(shown: Dict[str, dict], earlier: Dict[str, dict], turn: Path) -> dict:
    """A repo's last-blocked record: what the check just run `shown`, the hook and the `turn` it came from, and the
    commit blocks that stay behind it as `earlier`."""
    return {"pending": shown, "where": ledger.HOOK.where, "turn": str(turn), **({"earlier": earlier} if earlier else {})}


def accept_allowed() -> bool:
    """Whether `broom known --accept` works here: `BROOM_NO_ACCEPT` (set to anything but 0) turns it off, for
    agents that must fix what they break instead of accepting it."""
    return os.environ.get("BROOM_NO_ACCEPT", "") in ("", "0")


def refusal(repo: Path, left: Dict[str, dict]) -> str:
    """Why `broom known --accept` left these pending issues, each a smell that was past its hard limit and grew, out:
    what to bring each back to."""
    rows = sorted(left.values(), key=lambda e: (str(e.get("file")), e.get("line") or 0))
    if len(rows) == 1:
        return (f"broom: 1 can't be accepted: it was already past the hard limit and grew; bring it back to "
                f"{rows[0]['grown_from']} or fewer, or extract what you added")
    sizes = " and ".join(f"{e['grown_from']} ({rel(Path(str(e.get('file'))), repo)}:{e.get('line')})" for e in rows)
    return (f"broom: {len(rows)} can't be accepted: they were already past the hard limit and grew; bring them back "
            f"to {sizes} or fewer, or extract what you added")


def accept_blocked(repo: Path, why: str, *, agreed: bool = False) -> Tuple[int, str]:
    """Record the issues of the last commit or turn end broom blocked in `repo` as known, with the reason, and with
    `agreed` when the user agreed to leave them. Returns how many, and the hook that blocked them (`commit` when none
    is recorded). A smell that was past its hard limit and grew can't be accepted: it stays pending, and a line says
    so; with nothing else to accept the command exits."""
    state = load_json(COMMITS, {})
    prior = state.get(str(repo)) or {}
    pending = prior.get("pending") or {}
    where = prior.get("where") or "commit"
    left = {k: v for k, v in pending.items() if v.get("grown_from") is not None}
    pending = {k: v for k, v in pending.items() if k not in left}
    if left and not pending:
        raise SystemExit(refusal(repo, left))
    if left:
        say(refusal(repo, left))
    if pending:
        now = time.time()
        once = [k for k, v in pending.items() if v.get("tool") == TESTS_TOOL]  # no test ran: accepted for this turn only
        baseline_add_entries({k: {**v, "t": now, "why": why} for k, v in pending.items() if k not in once})
        turn = Path(prior["turn"]) if prior.get("turn") else None
        ledger.let_through(pending, "accept", turn, why=why, where=where, agreed=agreed or None)
        if turn is not None and once:
            ledger.note_turn(turn, ledger.ACCEPTED_HERE, [{"key": k} for k in once])
        if left or prior.get("earlier"):
            state[str(repo)] = {**prior, "pending": left}
        else:
            state.pop(str(repo), None)
        save_commits(state, [repo])
    return len(pending), where


def baseline_under(roots: List[Path]) -> Dict[str, dict]:
    """Known issues in files under any of `roots`."""
    out = {}
    for k, v in baseline_load().items():
        f = Path(str(v.get("file", "")))
        if any(f == r or r in f.parents for r in roots):
            out[k] = v
    return out


def baseline_remove(keys: List[str]) -> None:
    """Remove the baseline entries for `keys` from disk, under the file's lock; keys not there are ignored."""
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
    """`p` as text for a person: under the home directory it starts with "~" instead of the full path."""
    home = str(Path.home())
    s = str(p)
    return "~" + s[len(home):] if s.startswith(home) else s


def rel(f: Path, root: Path) -> str:
    """`f` relative to `root` when it lies under it, else as display() shows it."""
    try:
        return str(f.relative_to(root))
    except ValueError:
        return display(f)


def note_text(n: str) -> str:
    """The message part of a note: the text after "timeout:", "missing:" or "optional:", or the note itself."""
    return n.split(":", 1)[1] if n.startswith(("timeout:", "missing:", OPTIONAL_NOTE)) else n


def setup_hint(notes: List[str]) -> str:
    """A one-line hint to run /broom:setup when a note reports a missing tool; "" when none does."""
    missing = [n for n in notes if n.startswith("missing:")]
    return "Some checks couldn't run because tools are missing: offer the user /broom:setup." if missing else ""


def listing(issues: List[Issue], files: Set[Path]) -> List[Tuple[Issue, List[str]]]:
    """Each finding in the order the report shows them (grouped by tool and root, then by file and line), with the
    lines it takes: its own, and before it the header of its group when it is the group's first."""
    groups: Dict[Tuple[str, Path], List[Issue]] = {}
    for i in issues:
        groups.setdefault((i.tool, i.root), []).append(i)
    out = []
    for (tool, root), items in groups.items():
        for n, i in enumerate(sorted(items, key=lambda x: (str(x.file), x.line, x.col))):
            where = f"{rel(i.file, root)}:{i.line}:{i.col}" if i.line else rel(i.file, root)
            tag = "" if i.file in files or not files else "  [not in the changed files]"
            if i.grown_from is not None:
                tag += f"  [can't be accepted: was {i.grown_from}, already past the hard limit]"
            head = [f"\n{tool} ({display(root)}):"] if n == 0 else []
            out.append((i, head + [f"  {where}  {i.rule}  {i.msg}{tag}"]))
    return out


def size(lines: List[str]) -> int:
    """The characters `lines` take once joined, a newline after each."""
    return sum(len(x) + 1 for x in lines)


def fit(entries: List[Tuple[Issue, List[str]]], budget: int) -> Tuple[List[str], int]:
    """The lines of as many findings as `budget` characters and MAX_SHOWN allow (the first always), and how many."""
    out: List[str] = []
    shown = 0
    for _, lines in entries[:MAX_SHOWN]:
        if shown and size(out) + size(lines) > budget:
            break
        out += lines
        shown += 1
    return out, shown


def guidance(entries: List[Tuple[Issue, List[str]]], way_out: Optional[str]) -> List[str]:
    """The lines a block message ends its findings with: how to fix each kind of smell found, in the order the kinds
    first appear (what a linter reports says its own fix), what is not a fix, and then `way_out`. None for a
    report that isn't a block."""
    if way_out is None:
        return []
    fix = how_to_fix(i.rule for i, _ in entries if i.tool in ("smells", TESTS_TOOL))
    return (["\n" + "\n".join(fix)] if fix else []) + ["\n" + way_out]


def skipped(notes: List[str]) -> List[str]:
    """The lines saying which checks didn't run, and the setup offer when a tool is missing."""
    if not notes:
        return []
    return ["\nSkipped: " + "; ".join(note_text(n) for n in notes), *filter(None, [setup_hint(notes)])]


def render(head: str, issues: List[Issue], notes: List[str], files: Set[Path], way_out: Optional[str] = None) -> str:
    """The report Claude reads: `head`, the findings (at most MAX_SHOWN, fewer to keep the whole under MAX_CHARS,
    with how many more), then for a block (a `way_out` given) how to fix and the way out, then what was skipped."""
    entries = listing(issues, files)
    top = Counter(f"{i.tool} {i.rule}" for i in issues).most_common(10) if len(issues) > MAX_SHOWN else []
    before = [head] + (["\nMost frequent: " + ", ".join(f"{rule} ×{n}" for rule, n in top)] if top else [])
    after = guidance(entries, way_out) + skipped(notes)
    lines, shown = fit(entries, MAX_CHARS - size(before) - size(after) - MORE_ROOM)
    more = [f"\n... and {len(issues) - shown} more"] if len(issues) > shown else []
    return "\n".join(before + lines + more + after)


def new_notes(state: Path, notes: List[str], home: Path) -> List[str]:
    """Notes not shown before in this session, so a missing tool is mentioned once, not every time. Each fresh
    timeout or missing-tool note goes in the ledger, with `home`, the directory the hook ran in. A note about an
    optional tool is never shown by a hook: nothing nags for a tool the user didn't ask for, and `broom diagnose` and
    `broom doctor` say it."""
    fresh: List[str] = []

    def add(seen_before: list) -> list:
        fresh[:] = [n for n in notes if n not in set(seen_before) and not n.startswith(OPTIONAL_NOTE)]
        return sorted(set(seen_before) | set(fresh))

    update_json(state, [], add)
    ledger.skipped(fresh, home)
    return fresh
