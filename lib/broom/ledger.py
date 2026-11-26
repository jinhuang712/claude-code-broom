"""The ledger: what broom did with each finding, one JSON line each, appended to `ledger.jsonl` in broom's data
directory. `broom report` reads it back.

A line holds `t` (epoch seconds, which only orders the lines), `v` (the version of broom that wrote it; older lines
have none), `repo` (the main worktree's root, so a repo and its linked worktrees share one record), `event`, `where`
(the hook: commit, pre-commit, stop, subagent-stop) and per event:

- block: a finding stopped a commit or a turn's end. `key` is the finding's key from gate.issue_key, `tool`, `rule`
  and `file` (relative to its own worktree's root) say which, `line` where it was, and `spot` (a hash of that line's
  text) lets a later check of the file tell it again when its message changed (comeback). Older lines have neither.
- fix: a block's finding is gone, and the check that found it ran over its file with its tool.
- pass: a finding was let through, with `how`: accept (with `why`, and `agreed` when the user agreed to leave it) or
  gave-up. Older lines also hold retry, denials, stop-again and turn-ended, which no longer occur.
- ask: Claude put a question to the user about a finding (`why` is the question). It is no outcome: the finding still
  awaits its fix or pass line.
- hint: a nit, a slight smell, was given as context, without a block.
- skip: a tool didn't run (`note` is the timeout or missing note, `tool` the tool).
- time: seconds one check (`check`) took in a hook.
- run: seconds a whole check of a commit or a turn's end took (`seconds`), once it ran a tool: lint, types and smells.
- error: a hook failed and let the action through.
- waiver: a change loosened the bar: `kind` (config, suppression or no-verify), `file` and a short `note`.

Writing is one append under the lock, never raises into a hook, and keeps the file bounded. A pass and a waiver are
also noted in the turn's directory, where the turn's end reads them for the one line the user sees (the turn summary).
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

from . import __version__
from .gitutil import git_root, main_worktree
from .state import DATA_ROOT, locked, short_hash
from .toolchain import lang_of

LEDGER = DATA_ROOT / "ledger.jsonl"
MAX_BYTES = 2_000_000  # over this at an append, the oldest lines go, down to three quarters of it
THROUGH = "through.jsonl"  # in a turn's directory: what the turn let through, for its summary
WAIVED = "waivers.jsonl"  # in a turn's directory: the self-waivers it saw, for its summary and so each counts once
ASKED = "asked.jsonl"  # in a turn's directory: the findings Claude asked the user about, which don't block this turn
RUNS = "test-runs.jsonl"  # in a turn's directory: the test commands the session started, and those that failed
ACCEPTED_HERE = "accepted-here.jsonl"  # in a turn's directory: findings accepted for this turn only, never as known
TURN_NOTES = (THROUGH, WAIVED, ASKED, RUNS, ACCEPTED_HERE)
SHOWN_GROUPS = 5
LOUD_ACCEPTS = 3  # findings a turn accepts on its own before the user's line opens loudly
SKIP_PREFIXES = ("timeout:", "missing:")
OUTCOME_EVENTS = ("block", "fix", "pass")  # the lines that tell where a finding stands


class Hook:
    """Which hook this process runs for. `broom hook <event>` sets it once, and every line says where it came from."""

    where = ""
    loosened = False  # this run saw a looser .broom.json: what it hides is not fixed


HOOK = Hook()


def begin(event: str) -> None:
    """Set the hook (`where`) that every line this process writes records. `broom hook <event>` calls it once, before
    the hook's logic runs."""
    HOOK.where = event
    HOOK.loosened = False


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
    """One ledger row for `event` in `repo`, stamped with the time and the hook (`write` adds broom's version); a
    field that is None or empty is left out."""
    row: dict = {"t": round(time.time(), 3), "repo": repo, "event": event, "where": HOOK.where}
    row.update({k: v for k, v in fields.items() if v not in (None, "")})
    return row


def finding(event: str, key: str, entry: dict, **more: object) -> dict:
    """A line about one finding, from its entry (gate.issue_entry)."""
    repo, rel = locate(Path(str(entry.get("file") or "")))
    return line(event, repo, key=key, tool=entry.get("tool"), rule=entry.get("rule"), file=rel, **more)


def read(path: Path, needle: str = "") -> Iterator[dict]:
    """The lines of a JSON-lines file; one that doesn't parse, a torn write, is passed over. With `needle`, only the
    lines whose raw text holds it are parsed, which keeps a read of one repo's lines cheap."""
    try:
        text = path.read_text()
    except OSError:
        return
    for raw in text.splitlines():
        if needle not in raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            yield row


# ---------------------------------------------------------------- writing


def trim() -> None:
    """Drop the oldest lines down to three quarters of MAX_BYTES, so the ledger stays bounded and isn't rewritten at
    every append."""
    kept = newest_within(LEDGER.read_text().splitlines(), MAX_BYTES * 3 // 4)
    tmp = LEDGER.with_name(f".{LEDGER.name}.{os.getpid()}.tmp")
    tmp.write_text("".join(raw + "\n" for raw in kept))
    tmp.replace(LEDGER)


def newest_within(rows: List[str], limit: int) -> List[str]:
    """The newest raw lines of `rows` that fit in `limit` bytes (newlines included), in their order; the older ones are
    dropped."""
    size, newest = 0, []
    for raw in reversed(rows):
        size += len(raw.encode()) + 1
        if size > limit:
            break
        newest.append(raw)
    return newest[::-1]


def write(rows: List[dict]) -> None:
    """Append `rows` in one write. A ledger that can't be written is no reason to stop a hook."""
    if not rows:
        return
    try:
        text = "".join(json.dumps({"v": __version__, **r}, separators=(",", ":"), default=str) + "\n" for r in rows)
        with locked(LEDGER):
            with open(LEDGER, "a") as f:
                f.write(text)
            if LEDGER.stat().st_size > MAX_BYTES:
                trim()
    except (OSError, ValueError, TypeError):
        pass


# ---------------------------------------------------------------- events


def blocked(entries: Dict[str, dict]) -> None:
    """Log a `block` line for each finding in `entries` (key to entry): each one stopped a commit or a turn's end."""
    write([finding("block", k, e, line=e.get("line") or None, spot=spot(Path(str(e.get("file") or "")), e.get("line")))
           for k, e in entries.items()])


def spot(file: Path, number: object) -> Optional[str]:
    """A short hash of the text of line `number` of `file`, stripped: where a finding is, whatever its line number or
    its message. None without a line or a file."""
    if not isinstance(number, int) or number < 1:
        return None
    try:
        rows = file.read_text(errors="replace").splitlines()
    except OSError:
        return None
    return short_hash(rows[number - 1].strip()) if number <= len(rows) else None


def hinted(entries: Dict[str, dict]) -> None:
    """Log a `hint` line for each finding in `entries` (key to entry): each was a note given to Claude as context, not
    a block."""
    write([finding("hint", k, e) for k, e in entries.items()])


def let_through(entries: Dict[str, dict], how: str, turn: Optional[Path] = None, **more: object) -> None:
    """Findings that went through. `turn` is the directory of the turn they went through in."""
    rows = [finding("pass", k, e, how=how, **more) for k, e in entries.items()]
    write(rows)
    if turn is not None and rows:
        note_through(turn, rows)


def fixes(prior: Dict[str, dict], now: Dict[str, dict], known: Set[str], files: List[Path], notes: List[str]
          ) -> Set[str]:
    """Findings of an earlier block that are gone, and really fixed; the keys of `prior` this check is done with
    come back: the fixed and the replaced, never the ones that stay open. `now` holds what blocks now, `known` what
    was accepted as known since: neither is gone. Anything else stays open: a commit of other files, a tool that
    didn't run, a finding whose key changed because its message or its line did and that is still there under the
    new key (a function cut from 120 lines to 110). That last case is told by the group: each finding of a file,
    tool and rule that is new now takes the place of one that is gone."""
    if HOOK.loosened:
        return set()  # a finding the looser config hides is gone and not fixed: every one stays open
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
    write(not_fixed_yet([finding("fix", k, e) for k, e in out.items()]))
    return set(gone)


def not_fixed_yet(rows: List[dict]) -> List[dict]:
    """The fix `rows` of findings whose last block, fix or pass line in the ledger isn't a fix already: a commit and a
    turn's end that both see a finding gone write its one fix line between them."""
    if not rows:
        return rows
    last = {(r.get("repo"), r.get("key")): r["event"] for r in read(LEDGER) if r.get("event") in OUTCOME_EVENTS}
    return [r for r in rows if last.get((r["repo"], r["key"])) != "fix"]


def group(entry: dict) -> Tuple[object, object, object]:
    """The (file, tool, rule) of a finding. `fixes` counts a vanished finding as replaced, not fixed, when a new one
    shares its group."""
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


def ran(repos: Iterable[Path], took: float) -> None:
    """A check of a commit or a turn's end ran at least one tool and took `took` seconds, all of it: one line per repo
    it covered."""
    write([line("run", repo_of(r), seconds=round(took, 2)) for r in repos])


def errored(error: Exception) -> None:
    """A hook failed: this runs in its last-resort handler, so whatever goes wrong here stays here."""
    try:
        write([line("error", repo_of(Path.cwd()), note=f"{type(error).__name__}: {error}"[:200])])
    except (OSError, ValueError, TypeError):
        pass


def waived(found: List[dict], turn: Optional[Path]) -> None:
    """Log a `waiver` line for each self-waiver in `found` (dicts of kind, repo, file, note and key, from waivers.py)
    that the turn hasn't seen yet, and note it in the turn's directory (`turn`) for its summary. Without a turn every
    one is written."""
    if not found:
        return
    HOOK.loosened = HOOK.loosened or any(w["kind"] == "config" for w in found)
    seen = {r.get("key") for r in read(turn / WAIVED)} if turn is not None else set()
    fresh = {w["key"]: w for w in found if w["key"] not in seen}.values()
    rows = [line("waiver", w["repo"], kind=w["kind"], file=w["file"], note=w["note"], key=w["key"]) for w in fresh]
    write(rows)
    if turn is not None and rows:
        note_turn(turn, WAIVED, rows)


# ---------------------------------------------------------------- which note covers which finding

NOTE_NAMES = {"golangci-lint": ("golangci-lint", "go:"), "go vet": ("go vet", "go:"), "clippy": ("clippy", "cargo"),
              "swift build": ("swift",)}
LANGUAGE_TOOLS = {"py": ("ruff",), "go": ("golangci-lint",), "js": ("oxlint",), "css": ("oxlint",),
                  "swift": ("swiftlint", "swiftc", "sourcekitd"), "rust": ("cargo",)}
PY_NATIVE = {"function_lines", "type_lines", "file_lines", "nested_ternary"}  # Python's own parser measures these
TOOLS_OF_RULE = {"duplicate_lines": ("jscpd",), "dead_code": ("jscpd",), "folder_cycle": ("dependency-cruiser",)}


def note_tool(note: str) -> str:
    """The tool a `timeout:` or `missing:` note is about: its first word after the prefix, or dependency-cruiser when
    the note names it."""
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


def note_turn(turn: Path, name: str, rows: List[dict]) -> None:
    """Append `rows` to the file `name` in the turn's directory. A turn directory that can't be written is skipped."""
    try:
        with open(turn / name, "a") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))
    except OSError:
        pass


def note_through(turn: Path, rows: List[dict]) -> None:
    """Append the pass `rows` to the turn's `through.jsonl`, which `through_line` reads at the turn's end."""
    note_turn(turn, THROUGH, [{"rule": r.get("rule", "?"), "how": r.get("how", "?"), "why": r.get("why", ""),
                               "agreed": bool(r.get("agreed"))} for r in rows])


def forget_through(turn: Path) -> None:
    """Delete what the turn noted (`through.jsonl`, `waivers.jsonl`, `asked.jsonl`), so that what the turn before let
    through, waived and asked about, never shown, isn't reported in this one. A missing file is fine."""
    for name in TURN_NOTES:
        try:
            (turn / name).unlink()
        except OSError:
            pass


def waiver_text(row: dict) -> str:
    """One self-waiver as the summary says it: `suppression in a.py`, `.broom.json smells_off +magic_numbers`,
    `no-verify`."""
    kind, file = row.get("kind", "?"), row.get("file", "")
    if kind == "config":
        return f"{file} {row.get('note', '')}".strip()
    return f"{kind} in {file}" if file else kind


def waiver_part(turn: Path) -> Tuple[int, str]:
    """How many self-waivers the turn saw, and a list of them (the same one twice as `x2`); (0, "") for none."""
    rows = list(read(turn / WAIVED))
    groups = Counter(waiver_text(r) for r in rows)
    parts = [text if n == 1 else f"{text} x{n}" for text, n in groups.most_common()]
    more = f", and {len(parts) - SHOWN_GROUPS} more" if len(parts) > SHOWN_GROUPS else ""
    return len(rows), ", ".join(parts[:SHOWN_GROUPS]) + more


def through_how(row: dict) -> str:
    """How a pass went through, as the summary says it: `gave-up`, `accepted: why` or `accepted, the user agreed: why`."""
    if row.get("how") != "accept":
        return str(row.get("how", "?"))
    return f"accepted, the user agreed: {row.get('why', '')}" if row.get("agreed") else f"accepted: {row.get('why', '')}"


def through_part(rows: List[dict]) -> str:
    """What the turn let through (the `rows` of its through.jsonl), grouped by rule and by how: `broom let 3 through
    this turn: 2 magic_numbers (gave-up), 1 function_lines (accepted: why)`; empty when it let nothing through."""
    if not rows:
        return ""
    groups = Counter((r.get("rule", "?"), through_how(r)) for r in rows)
    parts = [f"{n} {rule} ({how})" for (rule, how), n in groups.most_common()]
    more = f", and {len(parts) - SHOWN_GROUPS} more" if len(parts) > SHOWN_GROUPS else ""
    return f"broom let {len(rows)} through this turn: " + ", ".join(parts[:SHOWN_GROUPS]) + more


def loud_accepts(rows: List[dict]) -> str:
    """What opens the user's line when the turn accepted LOUD_ACCEPTS findings or more on its own, with no yes from the
    user: `broom: Claude ACCEPTED 4 findings this turn on its own:`; empty otherwise."""
    alone = sum(1 for r in rows if r.get("how") == "accept" and not r.get("agreed"))
    return f"broom: Claude ACCEPTED {alone} findings this turn on its own:" if alone >= LOUD_ACCEPTS else ""


def through_line(turn: Path) -> str:
    """What the turn let through and what it waived, as the one line the user sees at its end: the `through_part`
    (after `loud_accepts`, when it has something to say), then `2 self-waivers: suppression in a.py, ...`; with waivers
    alone `broom saw 2 self-waivers this turn: ...`. Empty when it did neither."""
    rows = list(read(turn / THROUGH))
    through = " ".join(x for x in (loud_accepts(rows), through_part(rows)) if x)
    count, waived_text = waiver_part(turn)
    if not count:
        return through
    noun = f"{count} self-waiver{'' if count == 1 else 's'}"
    return f"{through}; {noun}: {waived_text}" if through else f"broom saw {noun} this turn: {waived_text}"
