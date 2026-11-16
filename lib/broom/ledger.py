"""The ledger: what broom did with each finding, one JSON line each, appended to `ledger.jsonl` in broom's data
directory. `broom report` reads it back.

A line holds `t` (epoch seconds), `repo` (the main worktree's root, so a repo and its linked worktrees share one
record), `event`, `where` (the hook: commit, pre-commit, stop, subagent-stop) and per event:

- block: a finding stopped a commit or a turn's end. `key` is the finding's key from gate.issue_key, `tool`, `rule`
  and `file` (relative to its own worktree's root) say which.
- fix: a block's finding is gone, and the check that found it ran over its file with its tool.
- pass: a finding was let through, with `how`: retry, denials, accept (with `why`), stop-again, turn-ended or gave-up.
- hint: a smell hint was given as context, without a block.
- skip: a tool didn't run (`note` is the timeout or missing note, `tool` the tool).
- time: seconds one check (`check`) took in a hook.
- error: a hook failed and let the action through.

Writing is one append under the lock, never raises into a hook, and keeps the file bounded. A pass is also noted in
the turn's directory, where the turn's end reads it for the one line the user sees (the turn summary).
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .gitutil import git_root, main_worktree
from .state import DATA_ROOT, locked
from .toolchain import lang_of

LEDGER = DATA_ROOT / "ledger.jsonl"
MAX_BYTES = 2_000_000  # over this at an append, the oldest lines go
KEEP_DAYS = 90
THROUGH = "through.jsonl"  # in a turn's directory: what the turn let through, for its summary
SHOWN_GROUPS = 5
SKIP_PREFIXES = ("timeout:", "missing:")


class Hook:
    """Which hook this process runs for. `broom hook <event>` sets it once, and every line says where it came from."""

    where = ""


HOOK = Hook()


def begin(event: str) -> None:
    HOOK.where = event


# ---------------------------------------------------------------- lines


def locate(file: Path) -> Tuple[str, str]:
    """The repo a file is in (its main worktree) and its path relative to the root of its own worktree."""
    root = git_root(file.parent)
    if root is None:
        return str(file.parent), file.name
    try:
        return str(main_worktree(root)), str(file.resolve().relative_to(root))
    except ValueError:
        return str(main_worktree(root)), file.name


def repo_of(path: Path) -> str:
    """The repo a directory or file is in, as a line records it; the path itself outside any repo."""
    root = git_root(path if path.is_dir() else path.parent)
    return str(main_worktree(root)) if root else str(path)


def line(event: str, repo: str, **fields: object) -> dict:
    row: dict = {"t": round(time.time(), 3), "repo": repo, "event": event, "where": HOOK.where}
    row.update({k: v for k, v in fields.items() if v not in (None, "")})
    return row


def finding(event: str, key: str, entry: dict, **more: object) -> dict:
    """A line about one finding, from its entry (gate.issue_entry)."""
    repo, rel = locate(Path(str(entry.get("file") or "")))
    return line(event, repo, key=key, tool=entry.get("tool"), rule=entry.get("rule"), file=rel, **more)


def read(path: Path) -> Iterator[dict]:
    """The lines of a JSON-lines file; one that doesn't parse, a torn write, is passed over."""
    try:
        text = path.read_text()
    except OSError:
        return
    for raw in text.splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            yield row


# ---------------------------------------------------------------- writing


def trim() -> None:
    """Drop the lines older than KEEP_DAYS. A ledger still over the limit after that loses its oldest lines too,
    down to three quarters of it, so it stays bounded and isn't rewritten at every append."""
    cutoff = time.time() - KEEP_DAYS * 86400
    kept = [raw for raw in LEDGER.read_text().splitlines() if line_time(raw) >= cutoff]
    if sum(len(raw.encode()) + 1 for raw in kept) > MAX_BYTES:
        kept = newest_within(kept, MAX_BYTES * 3 // 4)
    tmp = LEDGER.with_name(f".{LEDGER.name}.{os.getpid()}.tmp")
    tmp.write_text("".join(raw + "\n" for raw in kept))
    tmp.replace(LEDGER)


def newest_within(rows: List[str], limit: int) -> List[str]:
    size, newest = 0, []
    for raw in reversed(rows):
        size += len(raw.encode()) + 1
        if size > limit:
            break
        newest.append(raw)
    return newest[::-1]


def line_time(raw: str) -> float:
    try:
        t = json.loads(raw).get("t", 0)
        return t if isinstance(t, (int, float)) else 0
    except (ValueError, AttributeError):
        return 0


def write(rows: List[dict]) -> None:
    """Append `rows` in one write. A ledger that can't be written is no reason to stop a hook."""
    if not rows:
        return
    try:
        text = "".join(json.dumps(r, separators=(",", ":"), default=str) + "\n" for r in rows)
        with locked(LEDGER):
            with open(LEDGER, "a") as f:
                f.write(text)
            if LEDGER.stat().st_size > MAX_BYTES:
                trim()
    except (OSError, ValueError, TypeError):
        pass


# ---------------------------------------------------------------- events


def blocked(entries: Dict[str, dict]) -> None:
    write([finding("block", k, e) for k, e in entries.items()])


def hinted(entries: Dict[str, dict]) -> None:
    write([finding("hint", k, e) for k, e in entries.items()])


def let_through(entries: Dict[str, dict], how: str, turn: Optional[Path] = None, **more: object) -> None:
    """Findings that went through. `turn` is the directory of the turn they went through in."""
    rows = [finding("pass", k, e, how=how, **more) for k, e in entries.items()]
    write(rows)
    if turn is not None and rows:
        note_through(turn, rows)


def fixes(prior: Dict[str, dict], now: Dict[str, dict], known: Set[str], files: List[Path], notes: List[str]) -> None:
    """Findings of an earlier block that are gone, and really fixed. `now` holds what blocks now, `known` what was
    accepted as known since: neither is gone. Anything else stays open: a commit of other files, a tool that didn't
    run, a finding whose key changed because its message or its line did and that is still there under the new key
    (a function cut from 120 lines to 110). That last case is told by the group: each finding of a file, tool and
    rule that is new now takes the place of one that is gone."""
    covered = {f.resolve() for f in files}
    skipped = [n for n in notes if n.startswith(SKIP_PREFIXES)]
    gone = {k: e for k, e in prior.items()
            if k not in now and k not in known and Path(str(e.get("file") or "")).resolve() in covered
            and not any(covers(n, e) for n in skipped)}
    replaced = Counter(group(e) for k, e in now.items() if k not in prior)
    out = {}
    for k, e in sorted(gone.items(), key=lambda kv: kv[1].get("line") or 0):
        if replaced[group(e)] > 0:
            replaced[group(e)] -= 1
        else:
            out[k] = e
    write([finding("fix", k, e) for k, e in out.items()])


def group(entry: dict) -> Tuple[object, object, object]:
    return entry.get("file"), entry.get("tool"), entry.get("rule")


def skipped(notes: List[str], home: Path) -> None:
    """The timeout and missing-tool notes not shown before in this session; `home` is where the hook ran."""
    repo = repo_of(home)
    write([line("skip", repo, tool=note_tool(n), note=n) for n in dict.fromkeys(notes) if n.startswith(SKIP_PREFIXES)])


def timed(seconds: Dict[str, float]) -> None:
    """How long each check took, by its key (`tool:directory`)."""
    rows = []
    for key, took in seconds.items():
        check, _, where = key.partition(":")
        rows.append(line("time", repo_of(Path(where)) if where else "", check=check, seconds=round(took, 2)))
    write(rows)


def errored(error: Exception) -> None:
    """A hook failed: this runs in its last-resort handler, so whatever goes wrong here stays here."""
    try:
        write([line("error", repo_of(Path.cwd()), note=f"{type(error).__name__}: {error}"[:200])])
    except (OSError, ValueError, TypeError):
        pass


# ---------------------------------------------------------------- which note covers which finding

NOTE_NAMES = {"golangci-lint": ("golangci-lint", "go:"), "go vet": ("go vet", "go:"), "clippy": ("clippy", "cargo"),
              "swift build": ("swift",)}
LANGUAGE_TOOLS = {"py": ("ruff",), "go": ("golangci-lint",), "js": ("oxlint",), "css": ("oxlint",),
                  "swift": ("swiftlint",), "rust": ("cargo",)}
PY_NATIVE = {"function_lines", "type_lines", "file_lines", "nested_ternary"}  # Python's own parser measures these
TOOLS_OF_RULE = {"duplicate_lines": ("jscpd",), "dead_code": ("jscpd",), "folder_cycle": ("dependency-cruiser",)}


def note_tool(note: str) -> str:
    text = note.split(":", 1)[1]
    first = re.split(r"[\s:]", text)[0]
    return "dependency-cruiser" if first == "the" and "dependency-cruiser" in text else first


def names_of(entry: dict) -> Tuple[str, ...]:
    """The names a note must mention to be about the tool that found `entry`. A smell comes from the measurement
    of its file's language, from the tool of its rule where that is another (jscpd, dependency-cruiser), or from a
    scan that ran out of time."""
    tool = str(entry.get("tool") or "")
    if tool != "smells":
        return NOTE_NAMES.get(tool, (tool,))
    lang = lang_of(Path(str(entry.get("file") or ""))) or ""
    own = () if lang == "py" and entry.get("rule") in PY_NATIVE else LANGUAGE_TOOLS.get(lang, ())
    return (*own, "smells", "scan", *TOOLS_OF_RULE.get(str(entry.get("rule")), ()))


def covers(note: str, entry: dict) -> bool:
    """Whether a timeout or missing-tool note is about the tool that found `entry`."""
    text = note.split(":", 1)[1].lower()
    return any(re.search(r"\b" + re.escape(name), text) for name in names_of(entry))


# ---------------------------------------------------------------- the turn summary


def note_through(turn: Path, rows: List[dict]) -> None:
    text = "".join(json.dumps({"rule": r.get("rule", "?"), "how": r.get("how", "?"), "why": r.get("why", "")}) + "\n"
                   for r in rows)
    try:
        with open(turn / THROUGH, "a") as f:
            f.write(text)
    except OSError:
        pass


def forget_through(turn: Path) -> None:
    try:
        (turn / THROUGH).unlink()
    except OSError:
        pass


def through_line(turn: Path) -> str:
    """What the turn let through, as the one line the user sees at its end; empty when it let nothing through."""
    rows = list(read(turn / THROUGH))
    if not rows:
        return ""
    groups = Counter((r.get("rule", "?"), r.get("how", "?"), r.get("why", "")) for r in rows)
    parts = [f"{n} {rule} ({f'accepted: {why}' if how == 'accept' else how})"
             for (rule, how, why), n in groups.most_common()]
    more = f", and {len(parts) - SHOWN_GROUPS} more" if len(parts) > SHOWN_GROUPS else ""
    return f"broom let {len(rows)} through this turn: " + ", ".join(parts[:SHOWN_GROUPS]) + more
