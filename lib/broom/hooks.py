"""Hook handlers. When each one does anything is set by the userConfig options `format_on` and `check_on`.

- commit (PreToolUse on `git commit`) and git's pre-commit hook: see commitgate.
- edit (PostToolUse on Edit, Write and Serena's edit tools): format per edit when format_on=edit, and record
  the file for the stop gate when check_on=stop, a subagent's edit for that subagent's own stop.
- prompt (UserPromptSubmit): note the working tree, so the turn's end also checks what Bash changed or committed.
- stop (Stop, and SubagentStop for a subagent): lint and type-check what the turn changed when check_on=stop, the
  default: it catches what Claude writes even when the user commits by hand, which the commit hook never sees.
  A turn that ends while background work runs waits for a later one.
- session (SessionStart): tell Claude the limits card (see card), and when the repo is missing tools or configs
  broom needs, ask Claude to offer the user /broom:setup. Hooks can't ask the user anything themselves; Claude does, with the user's consent. The smell
  note comes from a scan of HEAD, cached; session-scan, an async hook, runs the scan when there is none.

A turn's end blocks like a commit, once: accept what is left with `broom known --accept "<why>"` and stop again.
Stopping again without that still ends the turn, as broom never traps one, but records nothing as known: what is
left stays open and shows in the turn's summary.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import ledger, waivers
from .card import limits_card
from .checkup import check_up_time
from .commitgate import checked, entries_of, issues_by_repo, way_out
from .config import REPO_FILE, excluded, setting
from .doctor import describe, diagnose_cached, new_gaps
from .fmt import format_files
from .findings import Issue
from .gate import (
    COMMITS, baseline_keys, new_notes, note_text, render, save_commits, setup_hint, verdict,
)
from .gitutil import git_changed_files, git_root
from .hotspots import cached_summary, session_note, summary
from .state import append_line, emit, load_json, prune_sessions, save_json, session_dir, short_hash
from .toolchain import lang_of
from .turns import DEFERRED, changed_since_snapshot, paused, snapshot, turn_base, turn_dir, waiting

MAX_BLOCKS = 3  # how often a turn's end blocks before it gives up
STOPS = ("stop", "subagent-stop")  # the hooks of a turn's end, as the ledger and commits.json name them
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


def note_config(path: Path, sd: Path) -> None:
    """A repo's own .broom.json was edited: note now what it loosens against the turn's base. A `check_on` set to off,
    which no later check would see, is on record this way too."""
    root = git_root(path.parent)
    if root and path == root / REPO_FILE:
        ledger.waived(waivers.config_waivers(root, turn_base(sd, root)), sd)


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
    if path.name == REPO_FILE:
        note_config(path, sd)
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
    for name in ("edits.txt", "scan.txt", "gate.json", DEFERRED, *ledger.TURN_NOTES):
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
    """Claude stopped again without editing: the turn ends. Nothing becomes known: what is left, less what was
    accepted since, stays open, and is noted as let through with how `turn-ended`."""
    known = baseline_keys()
    left = {k: e for k, e in (gate.get("blocked") or {}).items() if k not in known}
    ledger.let_through(left, "turn-ended", d)
    finish(d, root, f"{len(left)} issue(s) left unfixed" if left else "")


def turn_head(count: int) -> str:
    """The first line of a turn-end block: what was found, and the first thing to do about it."""
    return f"[broom] {count} issue(s) in this turn's changes. Fix them before finishing."


def turn_way_out(repos: List[Path], cwd: Path) -> str:
    """The last of a turn-end block's own lines: accept what is left with a reason and stop again, or stop again and
    leave it open."""
    leave = "Stopping again ends the turn, but leaves the issues open: a commit still stops on them."
    return f"{way_out(repos or [cwd], cwd, 'stop again')} {leave}"


def note_turn_block(d: Path, groups: Dict[Path, List[Issue]]) -> None:
    """Keep what a turn-end block showed in each repo's last-blocked record (commits.json), where `broom known
    --accept` finds it, as it does what a commit blocked."""
    state = load_json(COMMITS, {})
    for repo, issues in groups.items():
        state[str(repo)] = {"pending": entries_of(issues), "where": ledger.HOOK.where, "turn": str(d)}
    save_commits(state, groups)


def forget_turn_blocks(d: Path) -> None:
    """The turn's end found nothing to block: drop what its blocks left in commits.json, so a later `broom known
    --accept` doesn't accept what is gone."""
    state = load_json(COMMITS, {})
    mine = [k for k, v in state.items() if isinstance(v, dict) and v.get("turn") == str(d) and v.get("where") in STOPS]
    for k in mine:
        state.pop(k)
    if mine:
        save_commits(state, mine)


def block_turn(d: Path, blocking: List[Issue], progress: dict, reason: str) -> None:
    """Block the turn's end with `reason`, and note what Claude was shown: in gate.json, so that stopping again ends
    the turn, and in commits.json, for `broom known --accept`."""
    found = entries_of(blocking)
    ledger.blocked(found)
    save_json(d / "gate.json", {"verdict": verdict(blocking), "count": len(blocking), **progress, "blocked": found})
    note_turn_block(d, issues_by_repo(blocking))
    emit({"decision": "block", "reason": reason})


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
    blocking, hints, notes = checked(files, turn_base(d, root), d)
    blocking += [s.issue() for s in hints]  # at a turn's end a hint stops Claude once: it cleans up now
    if gate.get("blocked"):
        ledger.fixes(gate["blocked"], entries_of(blocking), baseline_keys(), files, notes)
    if not blocking:
        forget_turn_blocks(d)
        fresh = new_notes(d / "notes.json", notes, files[0])
        tail = "; ".join(note_text(n) for n in fresh) + (" (run /broom:setup)" if setup_hint(fresh) else "")
        finish(d, root, tail if fresh else "")
        return
    blocks = int(gate.get("blocks", 0)) + 1
    if blocks > MAX_BLOCKS:
        ledger.let_through(entries_of(blocking), "gave-up", d)
        finish(d, root, f"gave up after {MAX_BLOCKS} rounds, {len(blocking)} issue(s) left")
        return
    groups = issues_by_repo(blocking)
    reason = render(turn_head(len(blocking)), blocking, new_notes(d / "notes.json", notes, files[0]), set(files),
                    turn_way_out(list(groups), cwd))
    block_turn(d, blocking, {"edits_at": mark, "blocks": blocks}, reason)


def hook_prompt(data: dict) -> None:
    """A new prompt starts a turn: note the working tree, so the turn's end sees what Bash changed or committed.
    Not while a gate is waiting or blocked: those changes still belong to the turn before. It runs as an async hook
    (0.2 s on a 2,376-file repo, which no prompt should wait for); Claude's first tool call comes seconds later."""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    root = git_root(cwd)
    d = turn_dir(data)
    if waiting(d) or (d / "gate.json").exists():
        return
    ledger.forget_through(d)  # what the turn before let through or waived was never shown: no stop hook ended it
    if root and setting("check_on", cwd) == "stop":
        snapshot(d, root)


# ---------------------------------------------------------------- session


def hook_session(data: dict) -> None:
    """Notes for Claude's first turn, which waits for this hook: so only what is quick, the cached doctor and the
    smell counts of a scan that already ran. The limits card comes first, then the offer of setup, then the smells."""
    repo = git_root(Path(data.get("cwd") or os.getcwd()).resolve())
    if repo is None:
        return
    sd = session_dir(data.get("session_id") or "cli")
    if str(repo) in read_lines(sd / "nudged.txt"):
        return  # once per session: a compaction or /clear doesn't repeat it
    diagnosis = diagnose_cached(repo)
    smells = session_note(repo, cached_summary(repo))
    notes = [n for n in (limits_card(repo, diagnosis), setup_note(repo, diagnosis), smells) if n]
    if smells:
        append_line(sd / "smells-noted.txt", str(repo))
    if not notes:
        return
    append_line(sd / "nudged.txt", str(repo))
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(notes)}})


def scan_note(repo: Path, sd: Path, data: Optional[dict]) -> Optional[str]:
    """The smell note from a scan's summary, unless this session was told it already."""
    note = session_note(repo, data)
    if note and str(repo) not in read_lines(sd / "smells-noted.txt"):
        append_line(sd / "smells-noted.txt", str(repo))
        return note
    return None


def hook_session_scan(data: dict) -> None:
    """The scan behind the smell note, in the background (an async hook) when HEAD has none cached; then the check-up
    (see checkup), which counts what the scan counted and the files' rot. What either has to say reaches Claude with
    its next turn."""
    repo = git_root(Path(data.get("cwd") or os.getcwd()).resolve())
    if repo is None or setting("smells", repo) == "off":
        return
    cached = cached_summary(repo)
    whole = cached is not None and not cached.get("partial")
    found = cached if whole else summary(repo)
    # With a whole cached scan, the session hook has already said what there is to say about the smells.
    notes = [None if whole else scan_note(repo, session_dir(data.get("session_id") or "cli"), found),
             check_up_time(repo, found)]
    told = [n for n in notes if n]
    if told:
        emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(told)}})


SETUP_NOTE_GAPS = 6  # how many gaps the session note names before "and N more"


def setup_note(repo: Path, diagnosis: dict) -> Optional[str]:
    """The note offering /broom:setup for the gaps in `diagnosis` that the user hasn't answered, or None."""
    found = new_gaps(repo, diagnosis)  # gaps the user already answered, in any repo, stay quiet
    if not found:
        return None
    more = f"; and {len(found) - SETUP_NOTE_GAPS} more" if len(found) > SETUP_NOTE_GAPS else ""
    summary = "; ".join(describe(i) for i in found[:SETUP_NOTE_GAPS]) + more
    return (f"broom (the code-hygiene plugin) found gaps in this repo: {summary}. At a natural point, and before "
            "your first commit here at the latest, offer the user /broom:setup. Don't install anything they haven't "
            "agreed to; if they decline, run `broom setup --dismiss` so broom stops asking, here and in other repos, "
            "until a new kind of gap turns up.")
