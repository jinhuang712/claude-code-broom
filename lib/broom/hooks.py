"""Hook handlers. When each one does anything is set by the userConfig options `format_on` and `check_on`.

- commit (PreToolUse on `git commit`) and git's pre-commit hook: see commitgate.
- edit (PostToolUse on Edit, Write and Serena's edit tools): format per edit when format_on=edit, and record
  the file for the stop gate when check_on=stop, a subagent's edit for that subagent's own stop.
- prompt (UserPromptSubmit): note the working tree, so the turn's end also checks what Bash changed or committed.
- stop (Stop, and SubagentStop for a subagent): lint and type-check what the turn changed when check_on=stop, the
  default: it catches what Claude writes even when the user commits by hand, which the commit hook never sees.
  A turn that ends while background work runs waits for a later one.
- session (SessionStart): when the repo is missing tools or configs broom needs, ask Claude to offer the user
  /broom:setup. Hooks can't ask the user anything themselves; Claude does, with the user's consent. The smell
  note comes from a scan of HEAD, cached; session-scan, an async hook, runs the scan when there is none.

A turn's end blocks like a commit, once: stopping again records what is left as known, but type errors and smells
past the hard limit stay out of that record, so the commit still stops on them.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

from . import ledger
from .commitgate import MAX_BLOCKS, checked, entries_of, sticky
from .config import excluded, setting
from .doctor import describe, diagnose_cached, new_gaps
from .fmt import format_files
from .findings import Issue
from .gate import baseline_add_entries, baseline_keys, issue_key, new_notes, note_text, render, setup_hint, verdict
from .gitutil import git_changed_files, git_root
from .hotspots import cached_summary, session_note, summary
from .state import append_line, emit, load_json, prune_sessions, save_json, session_dir, short_hash
from .toolchain import lang_of
from .turns import DEFERRED, changed_since_snapshot, paused, snapshot, turn_base, turn_dir, waiting

SERENA_ONE_FILE = re.compile(
    r"^mcp__.*serena.*__(replace_symbol_body|insert_after_symbol|insert_before_symbol|replace_content|create_text_file)$"
)
SERENA_MANY_FILES = re.compile(r"^mcp__.*serena.*__(rename_symbol|replace_in_files|safe_delete_symbol)$")


# ---------------------------------------------------------------- edit


def serena_path(rel: str, data: dict) -> Optional[Path]:
    p = Path(rel)
    if p.is_absolute():
        return p
    for base in (data.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR")):
        if base and (Path(base) / p).exists():
            return Path(base) / p
    return None


def hook_edit(data: dict) -> None:
    tool = data.get("tool_name") or ""
    args = data.get("tool_input") or {}
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    sd = turn_dir(data)
    path: Optional[Path] = None
    if tool in ("Edit", "Write", "MultiEdit"):
        path = Path(args["file_path"]) if args.get("file_path") else None
    elif SERENA_ONE_FILE.match(tool) and args.get("relative_path"):
        path = serena_path(args["relative_path"], data)
    elif SERENA_MANY_FILES.match(tool):
        # Which files a rename touched isn't in the call: the stop gate takes the repo's changed files instead.
        root = git_root(cwd)
        if root and setting("check_on", cwd) == "stop":
            append_line(sd / "scan.txt", str(root))
        return
    if path is None or not path.is_file():
        return
    path = path.resolve()
    if git_root(path.parent) is None or excluded(path):
        # Outside any repo is a scratch file, a draft script in a temp directory: no project's code. Ten style
        # findings in one subagent's draft once stopped its session's turn.
        return
    if setting("check_on", path) == "stop" and lang_of(path):
        append_line(sd / "edits.txt", str(path))
    if setting("format_on", path) == "edit":
        # Claude Code shows Claude the diff of a file changed on disk since its last read, so no message here.
        format_files([path], final=False, scope=setting("format_scope", path))


# ---------------------------------------------------------------- stop


def read_lines(path: Path) -> List[str]:
    try:
        return [x for x in path.read_text().splitlines() if x]
    except OSError:
        return []


def end_turn(d: Path, root: Optional[Path]) -> None:
    """Forget the turn's records; the working tree as it is now is where the next turn's changes start."""
    for name in ("edits.txt", "scan.txt", "gate.json", DEFERRED, ledger.THROUGH):
        try:
            (d / name).unlink()
        except OSError:
            pass
    if root:
        snapshot(d, root)


def finish(d: Path, root: Optional[Path], tail: str = "") -> None:
    """End the turn with one message for the user at most: what the turn let through, then `tail`, what else there
    is to say. A turn that let nothing through says only the tail, with a `broom:` before it."""
    summary = ledger.through_line(d)
    end_turn(d, root)
    if summary or tail:
        emit({"systemMessage": f"{summary}; {tail}" if summary and tail else summary or f"broom: {tail}"})


def turn_files(data: dict, d: Path, root: Optional[Path]) -> Tuple[List[Path], str]:
    """The code files the turn changed: recorded edits, a whole repo after a many-file Serena edit, and in the main
    session what changed or was committed since the prompt. And a mark that changes whenever any of them does."""
    recorded = read_lines(d / "edits.txt")
    scans = read_lines(d / "scan.txt")
    files = [Path(p) for p in recorded]
    for repo in dict.fromkeys(scans):
        files += git_changed_files(Path(repo))
    since = changed_since_snapshot(d, root) if root and not data.get("agent_id") else []
    mark = short_hash(f"{len(recorded)}|{len(scans)}|{sorted((str(f), f.stat().st_mtime_ns) for f in since)}")
    files = [f for f in dict.fromkeys(files + since) if lang_of(f) and f.is_file() and not excluded(f)]
    return files, mark


def stop_again(d: Path, root: Optional[Path], gate: dict) -> None:
    """Claude stopped again without editing: what is left is known, and the turn ends. A severe finding went
    through too, though it isn't known: the commit still stops on it."""
    pending = gate.get("pending") or {}
    baseline_add_entries(pending if isinstance(pending, dict) else {k: {"t": time.time()} for k in pending})
    blocked, kept = gate.get("blocked") or {}, set(gate.get("sticky") or [])
    ledger.let_through({k: e for k, e in blocked.items() if k not in kept}, "stop-again", d)
    ledger.let_through({k: e for k, e in blocked.items() if k in kept}, "turn-ended", d)
    finish(d, root, f"{gate.get('count', 0)} issue(s) left unfixed")


def block_turn(d: Path, blocking: List[Issue], notes: List[str], files: List[Path], progress: dict) -> None:
    """Block the turn's end, and note in gate.json what Claude was shown: stopping again records what is left as
    known; type errors and severe smells stay out, so a commit still stops on them."""
    found = entries_of(blocking)
    severe = [issue_key(i) for i in blocking if sticky(i)]
    ledger.blocked(found)
    save_json(d / "gate.json", {"verdict": verdict(blocking), "count": len(blocking), **progress,
                                "pending": {k: e for k, e in found.items() if k not in severe},
                                "blocked": found, "sticky": severe})
    head = (f"[broom] {len(blocking)} issue(s) in this turn's changes. Fix them before finishing. If one is "
            "pre-existing or a false positive, say so and stop again: broom doesn't block twice without a new edit.")
    shown = new_notes(d / "notes.json", notes, files[0])
    emit({"decision": "block", "reason": render(head, blocking, shown, set(files))})


def hook_stop(data: dict) -> None:
    """The turn's end, or with an agent_id a subagent's (SubagentStop), whose block goes to the subagent."""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    if setting("check_on", cwd) != "stop" or data.get("permission_mode") == "plan":
        return
    d = turn_dir(data)
    if paused(data, d):
        return  # the background work wakes a later turn, whose end checks this one's changes too
    prune_sessions()
    root = None if data.get("agent_id") else git_root(cwd)
    files, mark = turn_files(data, d, root)
    if not files:
        finish(d, root)
        return
    gate = load_json(d / "gate.json", {})
    if gate.get("verdict") and gate.get("edits_at") == mark:
        stop_again(d, root, gate)
        return
    blocking, hints, notes = checked(files, turn_base(d, root))
    blocking += [s.issue() for s in hints]  # at a turn's end a hint stops Claude once: it cleans up now
    if gate.get("blocked"):
        ledger.fixes(gate["blocked"], entries_of(blocking), baseline_keys(), files, notes)
    if not blocking:
        fresh = new_notes(d / "notes.json", notes, files[0])
        tail = "; ".join(note_text(n) for n in fresh) + (" (run /broom:setup)" if setup_hint(fresh) else "")
        finish(d, root, tail if fresh else "")
        return
    blocks = int(gate.get("blocks", 0)) + 1
    if blocks > MAX_BLOCKS:
        ledger.let_through(entries_of(blocking), "gave-up", d)
        finish(d, root, f"gave up after {MAX_BLOCKS} rounds, {len(blocking)} issue(s) left")
        return
    block_turn(d, blocking, notes, files, {"edits_at": mark, "blocks": blocks})


def hook_prompt(data: dict) -> None:
    """A new prompt starts a turn: note the working tree, so the turn's end sees what Bash changed or committed.
    Not while a gate is waiting or blocked: those changes still belong to the turn before. It runs as an async hook
    (0.2 s on a 2,376-file repo, which no prompt should wait for); Claude's first tool call comes seconds later."""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    root = git_root(cwd)
    d = turn_dir(data)
    if waiting(d) or (d / "gate.json").exists():
        return
    ledger.forget_through(d)  # what the turn before let through was never shown, as no stop hook ended that turn
    if root and setting("check_on", cwd) == "stop":
        snapshot(d, root)


# ---------------------------------------------------------------- session


def hook_session(data: dict) -> None:
    """Notes for Claude's first turn, which waits for this hook: so only what is quick, the cached doctor and the
    smell counts of a scan that already ran."""
    repo = git_root(Path(data.get("cwd") or os.getcwd()).resolve())
    if repo is None:
        return
    sd = session_dir(data.get("session_id") or "cli")
    if str(repo) in read_lines(sd / "nudged.txt"):
        return  # once per session: a compaction or /clear doesn't repeat it
    smells = session_note(repo, cached_summary(repo))
    notes = [n for n in (setup_note(repo), smells) if n]
    if smells:
        append_line(sd / "smells-noted.txt", str(repo))
    if not notes:
        return
    append_line(sd / "nudged.txt", str(repo))
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(notes)}})


def hook_session_scan(data: dict) -> None:
    """The scan behind the smell note, in the background (an async hook) when HEAD has none cached; the note
    reaches Claude with its next turn."""
    repo = git_root(Path(data.get("cwd") or os.getcwd()).resolve())
    cached = cached_summary(repo) if repo else None
    if repo is None or setting("smells", repo) == "off" or (cached is not None and not cached.get("partial")):
        return  # with a whole cached scan, the session hook has already said what there is to say
    sd = session_dir(data.get("session_id") or "cli")
    note = session_note(repo, summary(repo))
    if note and str(repo) not in read_lines(sd / "smells-noted.txt"):
        append_line(sd / "smells-noted.txt", str(repo))
        emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": note}})


SETUP_NOTE_GAPS = 6  # how many gaps the session note names before "and N more"


def setup_note(repo: Path) -> Optional[str]:
    found = new_gaps(repo, diagnose_cached(repo))  # gaps the user already answered, in any repo, stay quiet
    if not found:
        return None
    more = f"; and {len(found) - SETUP_NOTE_GAPS} more" if len(found) > SETUP_NOTE_GAPS else ""
    summary = "; ".join(describe(i) for i in found[:SETUP_NOTE_GAPS]) + more
    return (f"broom (the code-hygiene plugin) found gaps in this repo: {summary}. At a natural point, and before "
            "your first commit here at the latest, offer the user /broom:setup. Don't install anything they haven't "
            "agreed to; if they decline, run `broom setup --dismiss` so broom stops asking, here and in other repos, "
            "until a new kind of gap turns up.")
