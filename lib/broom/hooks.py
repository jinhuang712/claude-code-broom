"""Hook handlers. When each one does anything is set by the userConfig options `format_on` and `check_on`.

- commit (PreToolUse on `git commit`): format the files the commit takes, then lint and type-check them; deny
  the commit while issues remain. Runs unless an option is off.
- edit (PostToolUse on Edit, Write and Serena's edit tools): format per edit when format_on=edit, and record
  the file for the stop gate when check_on=stop, a subagent's edit for that subagent's own stop.
- prompt (UserPromptSubmit): note the working tree, so the turn's end also checks what Bash changed or committed.
- stop (Stop, and SubagentStop for a subagent): lint and type-check what the turn changed when check_on=stop, the
  default: it catches what Claude writes even when the user commits by hand, which the commit hook never sees.
  A turn that ends while background work runs waits for a later one.
- session (SessionStart): when the repo is missing tools or configs broom needs, ask Claude to offer the user
  /broom:setup. Hooks can't ask the user anything themselves; Claude does, with the user's consent. The smell
  note comes from a scan of HEAD, cached; session-scan, an async hook, runs the scan when there is none.

Lint findings Claude has already seen once pass the second time unchanged, so broom never traps Claude in a loop
over a false positive or an issue that predates it. Type and compile errors don't pass on a retry: they pass fixed,
or after Claude accepts them with `broom known --accept "<why>"`, which puts the reason on record.
"""

from __future__ import annotations

import os
import re
import shlex
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .checks import Issue, run_checks
from .common import (
    DATA_ROOT, ChangedLines, append_line, emit, excluded, git, git_changed_files, git_root, lang_of, load_json,
    prune_sessions, save_json, session_dir, setting, short_hash,
)
from .doctor import describe, diagnose_cached, new_gaps
from .fmt import format_files
from .gate import (
    COMMITS, accept_allowed, baseline_add, baseline_add_entries, baseline_keys, issue_entry, issue_key, new_notes,
    note_text, render, select, setup_hint, verdict,
)
from .gitcmd import parse, parse_commit, plan_commit
from .hotspots import cached_summary, session_note, summary
from .smells import Smell, gate_smells, hint_text
from .turns import DEFERRED, changed_since_snapshot, paused, snapshot, turn_base, turn_dir, waiting

MAX_BLOCKS = 3
SERENA_ONE_FILE = re.compile(
    r"^mcp__.*serena.*__(replace_symbol_body|insert_after_symbol|insert_before_symbol|replace_content|create_text_file)$"
)
SERENA_MANY_FILES = re.compile(r"^mcp__.*serena.*__(rename_symbol|replace_in_files|safe_delete_symbol)$")


# ---------------------------------------------------------------- commit


def claim(tool_use_id: Optional[str]) -> bool:
    """True for the first handler to see this tool call. `git -C x commit` and `git commit` are separate `if`
    conditions, and a command holding both would otherwise run the commit check twice at once."""
    if not tool_use_id:
        return True
    d = DATA_ROOT / "claims"
    d.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - 86400
    for old in d.iterdir():
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass
    try:
        os.close(os.open(str(d / re.sub(r"[^\w.-]", "_", tool_use_id)), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False


def checked(files: List[Path], sd: Path, base: str = "HEAD") -> Tuple[List[Issue], List[Smell], List[str]]:
    """What blocks (lint and type issues not yet known, smells past the hard limit), the smell hints, and notes,
    for what changed since `base`."""
    issues, notes = run_checks(files, sd / "slow.json")
    known = baseline_keys()
    blocking = select(issues, set(files), known, ChangedLines(base))
    hints: List[Smell] = []
    for repo, group in by_repo(files).items():
        smell_blocks, smell_hints, smell_notes = gate_smells(repo, group, known, base)
        blocking += smell_blocks
        hints += smell_hints
        notes += smell_notes
    return blocking, hints, notes


def sticky(i: Issue) -> bool:
    """Type and compile errors, and smells past their hard limit: they pass fixed or accepted, never on a retry."""
    return i.hard or i.severe


def block_head(count: int, hard: int, repo: Path, cwd: Path) -> str:
    head = f"[broom] Commit blocked: {count} issue(s) in the files being committed"
    if not hard:
        return (f"{head}. Fix them and commit again. If one is pre-existing or a false positive, say so and run the "
                "same commit again: broom lets an unchanged result through.")
    head = f"{head}, {hard} of them type errors or code smells past the hard limit, which don't pass on a retry."
    if not accept_allowed():
        return f"{head} Fix them and commit again; accepting them is off here (BROOM_NO_ACCEPT)."
    accept = 'broom known --accept "<why>"' + ("" if repo == cwd else f" {shlex.quote(str(repo))}")
    return (f"{head} Fix them and commit again. If they predate this change or are false positives, run "
            f"`{accept}`, then commit again.")


def hook_commit(data: dict) -> None:
    command = (data.get("tool_input") or {}).get("command") or ""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    ops = parse(command, cwd)
    if not any(op.kind == "commit" for op in ops) or not claim(data.get("tool_use_id")):
        return
    sd = session_dir(data.get("session_id") or "cli")
    state_path = COMMITS
    state = load_json(state_path, {})
    denials: List[str] = []
    context: List[str] = []
    for idx, op in enumerate(ops):
        if op.kind != "commit":
            continue
        spec = parse_commit(op)
        if spec.no_verify or spec.dry_run:
            continue
        adds = [a for a in ops[:idx] if a.kind == "add"]
        plan = plan_commit(spec, adds)
        if plan is None:
            continue
        plan.files = {f for f in plan.files if not excluded(f)}
        if not plan.files:
            continue
        format_on, check_on = setting("format_on", plan.repo), setting("check_on", plan.repo)
        if format_on != "off":
            fallbacks: List[str] = []
            changed = format_files(sorted(f for f in plan.files if f not in plan.partial),
                                   scope=setting("format_scope", plan.repo), notes=fallbacks)
            context += [f"broom: {n}" for n in fallbacks]
            restage = [str(p) for p, _ in changed if p in plan.restage]
            if restage:
                git(["add", "--", *restage], plan.repo)
            if changed:
                context.append("broom formatted " + ", ".join(f"{p.name} ({tool})" for p, tool in changed))
            if plan.partial:
                context.append("broom left partially staged files unformatted: "
                               + ", ".join(sorted(p.name for p in plan.partial)))
        if check_on == "off":
            continue
        files = sorted(f for f in plan.files if lang_of(f))
        blocking, hints, notes = checked(files, sd)
        if hints:
            context.append(hint_text(hints))
        key = str(plan.repo)
        prior = state.get(key, {})
        hard = sum(1 for i in blocking if sticky(i))
        seen = prior.get("verdict") == verdict(blocking) or int(prior.get("denials", 0)) >= MAX_BLOCKS
        if not blocking:
            state.pop(key, None)
            fresh = new_notes(sd / "notes.json", notes)
            if fresh:
                context.append("broom skipped: " + "; ".join(note_text(n) for n in fresh))
                if setup_hint(fresh):
                    context.append(setup_hint(fresh))
        elif seen and not hard:
            # Claude saw these lint findings and committed again unchanged: they are known, the commit goes ahead.
            baseline_add(blocking)
            state.pop(key, None)
            context.append(f"broom let the commit through with {len(blocking)} known issue(s)")
        else:
            # Type errors and severe smells never pass on a retry alone: fixed, or accepted with a reason on record.
            state[key] = {"verdict": verdict(blocking), "denials": int(prior.get("denials", 0)) + 1,
                          "pending": {issue_key(i): issue_entry(i) for i in blocking}}
            head = block_head(len(blocking), hard, plan.repo, cwd)
            denials.append(render(head, blocking, new_notes(sd / "notes.json", notes), set(files)))
    save_json(state_path, state)

    out: dict = {"hookEventName": "PreToolUse"}
    if denials:
        out["permissionDecision"] = "deny"
        out["permissionDecisionReason"] = "\n\n".join(denials + context)
    elif context:
        out["additionalContext"] = "; ".join(context)
    if len(out) > 1:
        emit({"hookSpecificOutput": out})


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
    if excluded(path):
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


def by_repo(files: List[Path]) -> Dict[Path, List[Path]]:
    groups: Dict[Path, List[Path]] = {}
    for f in files:
        root = git_root(f.parent)
        if root:
            groups.setdefault(root, []).append(f)
    return groups


def end_turn(d: Path, root: Optional[Path]) -> None:
    """Forget the turn's records; the working tree as it is now is where the next turn's changes start."""
    for name in ("edits.txt", "scan.txt", "gate.json", DEFERRED):
        try:
            (d / name).unlink()
        except OSError:
            pass
    if root:
        snapshot(d, root)


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
        end_turn(d, root)
        return

    gate = load_json(d / "gate.json", {})
    if gate.get("verdict") and gate.get("edits_at") == mark:
        # Claude stopped again without editing: what is left is known, and the turn ends.
        pending = gate.get("pending") or {}
        baseline_add_entries(pending if isinstance(pending, dict) else {k: {"t": time.time()} for k in pending})
        end_turn(d, root)
        emit({"systemMessage": f"broom: {gate.get('count', 0)} issue(s) left unfixed"})
        return

    blocking, hints, notes = checked(files, d, turn_base(d, root))
    blocking += [s.issue() for s in hints]  # at a turn's end a hint stops Claude once: it cleans up now
    if not blocking:
        end_turn(d, root)
        fresh = new_notes(d / "notes.json", notes)
        if fresh:
            hint = " (run /broom:setup)" if setup_hint(fresh) else ""
            emit({"systemMessage": "broom: " + "; ".join(note_text(n) for n in fresh) + hint})
        return
    blocks = int(gate.get("blocks", 0)) + 1
    if blocks > MAX_BLOCKS:
        end_turn(d, root)
        emit({"systemMessage": f"broom: gave up after {MAX_BLOCKS} rounds, {len(blocking)} issue(s) left"})
        return
    # Stopping again records what is left as known; type errors and severe smells stay out, so a commit still
    # stops on them.
    pending = {issue_key(i): issue_entry(i) for i in blocking if not sticky(i)}
    save_json(d / "gate.json", {"verdict": verdict(blocking), "edits_at": mark, "blocks": blocks,
                                "count": len(blocking), "pending": pending})
    head = (f"[broom] {len(blocking)} issue(s) in this turn's changes. Fix them before finishing. If one is "
            "pre-existing or a false positive, say so and stop again: broom doesn't block twice without a new edit.")
    emit({"decision": "block", "reason": render(head, blocking, new_notes(d / "notes.json", notes), set(files))})


def hook_prompt(data: dict) -> None:
    """A new prompt starts a turn: note the working tree, so the turn's end sees what Bash changed or committed.
    Not while a gate is waiting or blocked: those changes still belong to the turn before. It runs as an async hook
    (0.2 s on a 2,376-file repo, which no prompt should wait for); Claude's first tool call comes seconds later."""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    root = git_root(cwd)
    d = turn_dir(data)
    if root and setting("check_on", cwd) == "stop" and not waiting(d) and not (d / "gate.json").exists():
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
    if repo is None or setting("smells", repo) == "off" or cached_summary(repo) is not None:
        return  # with a cached scan, the session hook has already said what there is to say
    sd = session_dir(data.get("session_id") or "cli")
    note = session_note(repo, summary(repo))
    if note and str(repo) not in read_lines(sd / "smells-noted.txt"):
        append_line(sd / "smells-noted.txt", str(repo))
        emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": note}})


def setup_note(repo: Path) -> Optional[str]:
    found = new_gaps(repo, diagnose_cached(repo))  # gaps the user already answered, in any repo, stay quiet
    if not found:
        return None
    summary = "; ".join(describe(i) for i in found[:6]) + (f"; and {len(found) - 6} more" if len(found) > 6 else "")
    return (f"broom (the code-hygiene plugin) found gaps in this repo: {summary}. At a natural point, and before "
            "your first commit here at the latest, offer the user /broom:setup. Don't install anything they haven't "
            "agreed to; if they decline, run `broom setup --dismiss` so broom stops asking, here and in other repos, "
            "until a new kind of gap turns up.")
