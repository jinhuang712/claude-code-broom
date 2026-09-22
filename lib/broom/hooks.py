"""Hook handlers. When each one does anything is set by the userConfig options `format_on` and `check_on`.

- commit (PreToolUse on `git commit`): format the files the commit takes, then lint and type-check them; deny
  the commit while issues remain. The default for both options.
- edit (PostToolUse on Edit, Write and Serena's edit tools): format per edit when format_on=edit, and record
  the file for the stop gate when check_on=stop.
- stop (Stop): lint and type-check the files edited this turn when check_on=stop.
- session (SessionStart): when the repo is missing tools or configs broom needs, ask Claude to offer the user
  /broom:setup. Hooks can't ask the user anything themselves; Claude does, with the user's consent.

A result Claude has already seen once passes the second time unchanged, so broom never traps Claude in a loop
over a false positive or an issue that predates it.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import List, Optional

from .checks import run_checks
from .common import (
    DATA_ROOT, append_line, emit, excluded, git, git_changed_files, git_root, lang_of, load_json, prune_sessions,
    save_json, session_dir, setting,
)
from .doctor import describe, diagnose_cached, gaps, needs_setup
from .fmt import format_files
from .gate import (
    baseline_add, baseline_add_entries, baseline_keys, issue_entry, issue_key, new_notes, note_text, render, select,
    setup_hint, verdict,
)
from .gitcmd import parse, parse_commit, plan_commit

MAX_BLOCKS = 3
EDITING_TASKS = {"subagent", "workflow", "teammate"}
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


def hook_commit(data: dict) -> None:
    command = (data.get("tool_input") or {}).get("command") or ""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    ops = parse(command, cwd)
    if not any(op.kind == "commit" for op in ops) or not claim(data.get("tool_use_id")):
        return
    sd = session_dir(data.get("session_id") or "cli")
    state_path = DATA_ROOT / "commits.json"
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
        issues, notes = run_checks(files, sd / "slow.json")
        blocking = select(issues, set(files), baseline_keys())
        key = str(plan.repo)
        prior = state.get(key, {})
        if not blocking:
            state.pop(key, None)
            fresh = new_notes(sd / "notes.json", notes)
            if fresh:
                context.append("broom skipped: " + "; ".join(note_text(n) for n in fresh))
                if setup_hint(fresh):
                    context.append(setup_hint(fresh))
        elif prior.get("verdict") == verdict(blocking) or int(prior.get("denials", 0)) >= MAX_BLOCKS:
            # Claude saw this result and committed again unchanged: the issues are known, the commit goes ahead.
            baseline_add(blocking)
            state.pop(key, None)
            context.append(f"broom let the commit through with {len(blocking)} known issue(s)")
        else:
            state[key] = {"verdict": verdict(blocking), "denials": int(prior.get("denials", 0)) + 1}
            head = (f"[broom] Commit blocked: {len(blocking)} issue(s) in the files being committed. Fix them "
                    "and commit again. If one is pre-existing or a false positive, say so and run the same commit "
                    "again: broom lets an unchanged result through.")
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
    sd = session_dir(data.get("session_id") or "cli")
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


def clear_turn(sd: Path) -> None:
    for name in ("edits.txt", "scan.txt", "gate.json"):
        try:
            (sd / name).unlink()
        except OSError:
            pass


def hook_stop(data: dict) -> None:
    if setting("check_on", Path(data.get("cwd") or os.getcwd())) != "stop" or data.get("permission_mode") == "plan":
        return
    if any(isinstance(t, dict) and t.get("type") in EDITING_TASKS for t in data.get("background_tasks") or []):
        return  # a background agent may still be editing
    prune_sessions()
    sd = session_dir(data.get("session_id") or "cli")
    recorded = read_lines(sd / "edits.txt")
    scans = read_lines(sd / "scan.txt")
    edit_count = len(recorded) + len(scans)
    files = [Path(p) for p in recorded]
    for root in dict.fromkeys(scans):
        files += git_changed_files(Path(root))
    files = [f for f in dict.fromkeys(files) if lang_of(f) and f.is_file() and not excluded(f)]
    if not files:
        clear_turn(sd)
        return

    gate = load_json(sd / "gate.json", {})
    if gate.get("verdict") and gate.get("edits_at") == edit_count:
        # Claude stopped again without editing: what is left is known, and the turn ends.
        pending = gate.get("pending") or {}
        baseline_add_entries(pending if isinstance(pending, dict) else {k: {"t": time.time()} for k in pending})
        clear_turn(sd)
        emit({"systemMessage": f"broom: {gate.get('count', 0)} issue(s) left unfixed"})
        return

    issues, notes = run_checks(files, sd / "slow.json")
    blocking = select(issues, set(files), baseline_keys())
    if not blocking:
        clear_turn(sd)
        fresh = new_notes(sd / "notes.json", notes)
        if fresh:
            hint = " (run /broom:setup)" if setup_hint(fresh) else ""
            emit({"systemMessage": "broom: " + "; ".join(note_text(n) for n in fresh) + hint})
        return
    blocks = int(gate.get("blocks", 0)) + 1
    if blocks > MAX_BLOCKS:
        clear_turn(sd)
        emit({"systemMessage": f"broom: gave up after {MAX_BLOCKS} rounds, {len(blocking)} issue(s) left"})
        return
    save_json(sd / "gate.json", {"verdict": verdict(blocking), "edits_at": edit_count, "blocks": blocks,
                                 "count": len(blocking), "pending": {issue_key(i): issue_entry(i) for i in blocking}})
    head = (f"[broom] {len(blocking)} issue(s) in this turn's changes. Fix them before finishing. If one is "
            "pre-existing or a false positive, say so and stop again: broom doesn't block twice without a new edit.")
    emit({"decision": "block", "reason": render(head, blocking, new_notes(sd / "notes.json", notes), set(files))})


# ---------------------------------------------------------------- session


def hook_session(data: dict) -> None:
    repo = git_root(Path(data.get("cwd") or os.getcwd()).resolve())
    if repo is None:
        return
    sd = session_dir(data.get("session_id") or "cli")
    if str(repo) in read_lines(sd / "nudged.txt"):
        return  # once per session: a compaction or /clear doesn't repeat it
    result = diagnose_cached(repo)
    if not needs_setup(repo, result):
        return
    append_line(sd / "nudged.txt", str(repo))
    found = gaps(result)
    summary = "; ".join(describe(i) for i in found[:6]) + (f"; and {len(found) - 6} more" if len(found) > 6 else "")
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": (
        f"broom (the code-hygiene plugin) found gaps in this repo: {summary}. At a natural point, and before your "
        "first commit here at the latest, offer the user /broom:setup. Don't install anything they haven't agreed "
        "to; if they decline, run `broom setup --dismiss` so broom stops asking until something changes."
    )}})
