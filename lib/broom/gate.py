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

from . import ledger, repodata
from .findings import Issue
from .config import OPTIONAL_NOTE, TESTS_NOT_RUN, TESTS_TOOL, excluded, repo_config
from .fixes import how_to_fix
from .gitutil import ChangedLines, git_root, main_worktree, worktrees
from .state import load_json, say, short_hash, update_json

STOPS = ("stop", "subagent-stop")  # the hooks of a turn's end, as the ledger and commits.json name them
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


def checkout_path(f: Path) -> Path:
    """`f` as the main checkout of its repo names it: a file or a folder of a linked worktree is the one at the same
    place under the main checkout, and any other path is itself."""
    root = git_root(f if f.is_dir() else f.parent)
    main = main_worktree(root) if root else None
    if main is None or main == root:
        return f
    try:
        return main / f.resolve().relative_to(root)
    except ValueError:
        return f


def issue_key(i: Issue) -> str:
    """A short id for a finding: its file, tool, rule and message plus the text of its line, not its number."""
    # Keyed on the line's text, not its number, so a known issue stays known when lines above it move. And on the file
    # as the main checkout names it, so what was accepted in a linked worktree stays known once the work lands.
    return key_of(checkout_path(i.file), i.tool, i.rule, i.msg, line_text(i.file, i.line))


def key_of(file: Path, tool: str, rule: str, msg: str, text: str) -> str:
    """The id of a finding from its parts: `file` as the main checkout names it, and `text`, its line stripped. The
    file is keyed relative to the main checkout (repodata.key_path), so a repo moved elsewhere keeps its keys."""
    return short_hash(f"{repodata.key_path(file)}|{tool}|{rule}|{msg}|{text}")


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


def mains(places: Iterable[Path]) -> Set[Optional[Path]]:
    """The main checkouts of the repos that hold `places`; None for a place in no repo."""
    return {repodata.main_of(p) for p in places}


def store(main: Optional[Path], name: str, *, write: bool = False) -> Path:
    """The record `name` of the repo whose main checkout is `main` (the folder outside any repo for None)."""
    if main is None:
        return repodata.OUTSIDE / name  # save_json makes the folder
    return (repodata.made(main) if write else repodata.folder(main)) / name


def absolute(main: Optional[Path], entries: Dict[str, dict]) -> Dict[str, dict]:
    """Known issues as the repo's folder keeps them, each file relative to `main`, with each file made whole."""
    if main is None:
        return entries
    return {k: {**e, "file": str(main / str(e["file"]))} if e.get("file") and not Path(str(e["file"])).is_absolute()
            else e for k, e in entries.items()}


def relative(entries: Dict[str, dict]) -> Dict[str, dict]:
    """Known issues as the repo's folder keeps them: each file relative to its main checkout."""
    return {k: {**e, "file": repodata.key_path(Path(str(e["file"])))} if e.get("file") else e
            for k, e in entries.items()}


def stored(main: Optional[Path]) -> Dict[str, dict]:
    """The known issues of one repo, keyed by issue key, each file whole; empty when there are none."""
    return absolute(main, baseline_entries(load_json(store(main, repodata.BASELINE), {})))


def baseline_load(places: Iterable[Path]) -> Dict[str, dict]:
    """The known issues of the repos that hold `places`, keyed by issue key; empty when there are none."""
    out: Dict[str, dict] = {}
    for main in mains(places):
        out.update(stored(main))
    return out


def baseline_keys(places: Iterable[Path]) -> Set[str]:
    """The keys of the known issues of the repos that hold `places`, for telling which findings are already known."""
    return set(baseline_load(places))


def baseline_change(main: Optional[Path], change) -> None:
    """Let `change(entries)` change one repo's known issues (each file whole) and write them back, under the lock."""
    def apply(raw: dict) -> dict:
        data = absolute(main, baseline_entries(raw))
        result = change(data)
        return relative(data if result is None else result)

    update_json(store(main, repodata.BASELINE, write=True), {}, apply)


def baseline_add_entries(entries: Dict[str, dict]) -> None:
    """Add `entries` to the known issues of their files' repos, under each file's lock. An entry never expires
    (decision 046): its key holds the text of its line, so it stops matching once that code changes, and `broom known
    --clear` removes it."""
    groups: Dict[Optional[Path], Dict[str, dict]] = {}
    for k, e in entries.items():
        groups.setdefault(repodata.main_of(Path(str(e.get("file") or "/"))), {})[k] = e
    for main, part in groups.items():
        baseline_change(main, lambda data, part=part: data.update(part))


def load_commits(roots: Iterable[Path]) -> dict:
    """The last-blocked records of the worktree roots of the repos that hold `roots`, by worktree root."""
    state: dict = {}
    for main in mains(roots):
        raw = load_json(store(main, repodata.COMMITS), {})
        state.update(raw if isinstance(raw, dict) else {})
    return state


def save_commits(state: dict, repos: Iterable[Path]) -> None:
    """Write this run's repos' entries of the last-blocked record back to each repo's folder, and leave the other
    roots' as they are on disk: another hook may have changed them since this one read the file."""
    groups: Dict[Optional[Path], Set[str]] = {}
    for r in repos:
        groups.setdefault(repodata.main_of(Path(r)), set()).add(str(r))

    for main, keys in groups.items():
        def put(data: dict, keys: Set[str] = keys) -> None:
            for key in keys:
                if key in state:
                    data[key] = state[key]
                else:
                    data.pop(key, None)

        update_json(store(main, repodata.COMMITS, write=True), {}, put)


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
    state = load_commits([repo])
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
        once = {k: v for k, v in pending.items() if v.get("tool") == TESTS_TOOL}  # no test ran: accepted for this turn only
        mark = {"agreed": True} if agreed else {}
        baseline_add_entries({k: {**v, "file": str(checkout_path(Path(str(v.get("file") or "")))), "t": now, "why": why,
                                  **mark} for k, v in pending.items() if k not in once})
        turn = Path(prior["turn"]) if prior.get("turn") else None
        ledger.let_through(pending, "accept", turn, why=why, where=where, agreed=agreed or None)
        if turn is not None and once:
            ledger.note_turn(turn, ledger.ACCEPTED_HERE, [{"key": k, "rule": v.get("rule")} for k, v in once.items()])
        if left or prior.get("earlier"):
            state[str(repo)] = {**prior, "pending": left}
        else:
            state.pop(str(repo), None)
        save_commits(state, [repo])
    return len(pending), where


def baseline_under(roots: List[Path]) -> Dict[str, dict]:
    """Known issues in files under any of `roots`, each root as the main checkout names it: an accept keeps its file
    that way, so a linked worktree and the main checkout list the same ones."""
    out = {}
    every = baseline_load(roots)
    roots = [checkout_path(r) for r in roots]
    for k, v in every.items():
        f = Path(str(v.get("file", "")))
        if any(f == r or r in f.parents for r in roots):
            out[k] = v
    return out


def line_texts(places: Iterable[Path]) -> Set[str]:
    """The stripped text of every line of every readable file in `places`."""
    out: Set[str] = set()
    for f in places:
        try:
            out |= {row.strip() for row in f.read_text(errors="replace").splitlines()}
        except OSError:
            pass
    return out


def changed_code(entries: Dict[str, dict]) -> Set[str]:
    """The keys of `entries` (known issues) that no line of their file gives any more, in the main checkout or in a
    linked worktree of it: the code changed, so the entry hides nothing. A known issue never expires, so only this
    tells it is spent. An entry from before broom stored a file is left out: nothing says where to look."""
    gone: Set[str] = set()
    for key, e in entries.items():
        if not e.get("file"):
            continue
        f = checkout_path(Path(str(e["file"])))
        here = next((p for p in (f.parent, *f.parents) if p.is_dir()), None)
        root = git_root(here) if here else None
        places = [f] + [w / f.resolve().relative_to(root) for w in worktrees(root)] if root else [f]
        texts = line_texts(places) | (set() if e.get("line") else {""})  # a finding of the whole file has no line
        parts = (f, str(e.get("tool", "")), str(e.get("rule", "")), str(e.get("msg", "")))
        if key not in {key_of(*parts, t) for t in texts}:
            gone.add(key)
    return gone


def baseline_remove(keys: List[str], places: Iterable[Path]) -> None:
    """Remove the known issues for `keys` from the repos that hold `places`, under each file's lock; keys not there
    are ignored."""
    def drop(data: dict) -> None:
        for k in keys:
            data.pop(k, None)

    for main in mains(places):
        baseline_change(main, drop)


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
    bare = any(i.rule == TESTS_NOT_RUN and not repo_config(i.root).get("test_commands") for i, _ in entries)
    fix = how_to_fix((i.rule for i, _ in entries if i.tool in ("smells", TESTS_TOOL)), own_runner=bare)
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
