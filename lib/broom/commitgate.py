"""The commit gate: what stops a commit, for Claude Code's commit hook (PreToolUse on a Bash `git commit`) and for
git's own pre-commit hook, which `broom install-hook` adds for commits that hook never sees. The turn-end gate
checks with the same `checked`.

Lint findings Claude has already seen once pass the second time unchanged, so broom never traps Claude in a loop
over a false positive or an issue that predates it. Type and compile errors and smells past the hard limit don't
pass on a retry: they pass fixed, or after Claude accepts them with `broom known --accept "<why>"`, which puts the
reason on record.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .checks import Issue, run_checks
from .config import excluded, setting
from .fmt import format_files
from .gate import (
    COMMITS, accept_allowed, baseline_add, baseline_keys, issue_entry, issue_key, new_notes, note_text, render,
    select, setup_hint, verdict,
)
from .gitcmd import CommitPlan, GitOp, parse, parse_commit, plan_commit, staged
from .gitutil import ChangedLines, git, git_root
from .passed import record, staged_blobs, unpassed, worktree_blobs
from .smells import Smell, gate_smells, hint_text
from .state import DATA_ROOT, emit, load_json, save_json, session_dir
from .toolchain import lang_of

MAX_BLOCKS = 3


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


def by_repo(files: List[Path]) -> Dict[Path, List[Path]]:
    groups: Dict[Path, List[Path]] = {}
    for f in files:
        root = git_root(f.parent)
        if root:
            groups.setdefault(root, []).append(f)
    return groups


def checked(files: List[Path], sd: Path, base: str = "HEAD") -> Tuple[List[Issue], List[Smell], List[str]]:
    """What blocks (lint and type issues not yet known, smells past the hard limit), the smell hints, and notes,
    for what changed since `base`. Content that passed before isn't checked again; content that passes now is
    recorded."""
    files = [f for repo, group in by_repo(files).items() for f in unpassed(repo, group, worktree_blobs(repo, group))]
    if not files:
        return [], [], []
    issues, notes = run_checks(files, sd / "slow.json")
    known = baseline_keys()
    blocking = select(issues, set(files), known, ChangedLines(base))
    hints: List[Smell] = []
    for repo, group in by_repo(files).items():
        smell_blocks, smell_hints, smell_notes = gate_smells(repo, group, known, base)
        blocking += smell_blocks
        hints += smell_hints
        notes += smell_notes
    if not (blocking or hints or any(n.startswith("timeout:") for n in notes)):
        for repo, group in by_repo(files).items():
            record(repo, group)
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


def gate_files(repo: Path, files: List[Path], sd: Path, cwd: Path, state: dict) -> Tuple[Optional[str], List[str]]:
    """Check what a commit takes from `repo`: the denial when it must stop (else None), and lines of context.
    `state` holds each repo's last blocked commit, for the retry rule and `broom known --accept`."""
    files = sorted(f for f in files if lang_of(f))
    blocking, hints, notes = checked(files, sd)
    context = [hint_text(hints)] if hints else []
    key = str(repo)
    prior = state.get(key, {})
    hard = sum(1 for i in blocking if sticky(i))
    if not blocking:
        state.pop(key, None)
        fresh = new_notes(sd / "notes.json", notes)
        if fresh:
            context.append("broom skipped: " + "; ".join(note_text(n) for n in fresh))
            context += [setup_hint(fresh)] if setup_hint(fresh) else []
        return None, context
    if not hard and (prior.get("verdict") == verdict(blocking) or int(prior.get("denials", 0)) >= MAX_BLOCKS):
        # Claude saw these lint findings and committed again unchanged: they are known, the commit goes ahead.
        baseline_add(blocking)
        state.pop(key, None)
        return None, context + [f"broom let the commit through with {len(blocking)} known issue(s)"]
    # Type errors and severe smells never pass on a retry alone: fixed, or accepted with a reason on record.
    state[key] = {"verdict": verdict(blocking), "denials": int(prior.get("denials", 0)) + 1,
                  "pending": {issue_key(i): issue_entry(i) for i in blocking}}
    head = block_head(len(blocking), hard, repo, cwd)
    return render(head, blocking, new_notes(sd / "notes.json", notes), set(files)), context


def hook_pre_commit() -> int:
    """git's own pre-commit hook, which `broom install-hook` adds: the commit gate for commits Claude Code's hook
    never sees, a wrapper script's or a person's. It checks and doesn't format. Content that passed already, as at
    Claude's own `git commit`, goes through at once."""
    repo = git_root(Path.cwd().resolve())
    if repo is None or setting("check_on", repo) == "off":
        return 0
    files = [f for f in sorted(staged(repo)) if not excluded(f) and lang_of(f)]
    if not unpassed(repo, files, staged_blobs(repo, files)):
        return 0
    state = load_json(COMMITS, {})
    denial, context = gate_files(repo, files, session_dir("git-pre-commit"), repo, state)
    save_json(COMMITS, state)
    for line in context + ([denial] if denial else []):
        print(line, file=sys.stderr)
    return 1 if denial else 0


def commit_plans(ops: List[GitOp]) -> List[CommitPlan]:
    """What each commit in a Bash command takes, the commits `--no-verify` or `--dry-run` skip left out."""
    plans = []
    for idx, op in enumerate(ops):
        spec = parse_commit(op) if op.kind == "commit" else None
        if spec is None or spec.no_verify or spec.dry_run:
            continue
        plan = plan_commit(spec, [a for a in ops[:idx] if a.kind == "add"])
        if plan is not None:
            plan.files = {f for f in plan.files if not excluded(f)}
            plans += [plan] if plan.files else []
    return plans


def format_commit(plan: CommitPlan) -> List[str]:
    """Format what the commit takes, re-stage what was staged in full, and say what happened. A partly staged file
    is left alone: formatting and re-adding it would commit its unstaged hunks too."""
    fallbacks: List[str] = []
    changed = format_files(sorted(f for f in plan.files if f not in plan.partial),
                           scope=setting("format_scope", plan.repo), notes=fallbacks)
    restage = [str(p) for p, _ in changed if p in plan.restage]
    if restage:
        git(["add", "--", *restage], plan.repo)
    context = [f"broom: {n}" for n in fallbacks]
    context += ["broom formatted " + ", ".join(f"{p.name} ({tool})" for p, tool in changed)] if changed else []
    if plan.partial:
        context.append("broom left partially staged files unformatted: "
                       + ", ".join(sorted(p.name for p in plan.partial)))
    return context


def answer(denials: List[str], context: List[str]) -> None:
    out: dict = {"hookEventName": "PreToolUse"}
    if denials:
        out["permissionDecision"] = "deny"
        out["permissionDecisionReason"] = "\n\n".join(denials + context)
    elif context:
        out["additionalContext"] = "; ".join(context)
    if len(out) > 1:
        emit({"hookSpecificOutput": out})


def hook_commit(data: dict) -> None:
    """Claude Code's PreToolUse hook on Bash: format and check what each `git commit` in the command takes."""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    ops = parse((data.get("tool_input") or {}).get("command") or "", cwd)
    if not any(op.kind == "commit" for op in ops) or not claim(data.get("tool_use_id")):
        return
    sd = session_dir(data.get("session_id") or "cli")
    state = load_json(COMMITS, {})
    denials: List[str] = []
    context: List[str] = []
    for plan in commit_plans(ops):
        if setting("format_on", plan.repo) != "off":
            context += format_commit(plan)
        if setting("check_on", plan.repo) == "off":
            continue
        denial, more = gate_files(plan.repo, list(plan.files), sd, cwd, state)
        context += more
        denials += [denial] if denial else []
    save_json(COMMITS, state)
    answer(denials, context)
