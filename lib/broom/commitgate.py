"""The commit gate: what stops a commit, for Claude Code's commit hook (PreToolUse on a Bash `git commit`) and for
git's own pre-commit hook, which `broom install-hook` adds for commits that hook never sees. The turn-end gate
checks with the same `checked`.

Every blocking finding, lint included, passes fixed, or after Claude accepts it with `broom known --accept "<why>"`,
which puts the reason on record: a retry alone lets nothing through. A false positive or an issue that predates the
change costs one command.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from . import ledger
from .checks import SLOW_PATH, run_checks
from .findings import Issue
from .config import excluded, setting
from .fmt import format_files
from .gate import (
    COMMITS, accept_allowed, baseline_keys, issue_entry, issue_key, new_notes, note_text, render, save_commits,
    select, setup_hint,
)
from .gitcmd import CommitPlan, GitOp, parse, parse_commit, plan_commit, staged
from .githook import installed
from .gitutil import ChangedLines, git, git_root
from .passed import record, staged_blobs, unpassed, worktree_blobs
from .smells import Smell, gate_smells, hint_text
from .state import DATA_ROOT, emit, load_json, session_dir
from .toolchain import lang_of


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


def checked(files: List[Path], base: str = "HEAD") -> Tuple[List[Issue], List[Smell], List[str]]:
    """What blocks (lint and type issues not yet known, smells past the hard limit), the smell hints, and notes,
    for what changed since `base`. Content that passed before isn't checked again; content that passes now is
    recorded."""
    files = [f for repo, group in by_repo(files).items() for f in unpassed(repo, group, worktree_blobs(repo, group))]
    if not files:
        return [], [], []
    issues, notes = run_checks(files, SLOW_PATH)
    known = baseline_keys()
    blocking = select(issues, set(files), known, ChangedLines(base))
    hints: List[Smell] = []
    for repo, group in by_repo(files).items():
        smell_blocks, smell_hints, smell_notes = gate_smells(repo, group, known, base)
        blocking += smell_blocks
        hints += smell_hints
        notes += smell_notes
    record_passed(files, blocking, hints, notes)
    return blocking, hints, notes


def record_passed(files: List[Path], blocking: List[Issue], hints: List[Smell], notes: List[str]) -> None:
    """Record each file nothing stopped and nothing hinted, so one file with a finding doesn't make the rest run
    again at the next try. A timeout, or a finding outside these files (a type error in a file they affect),
    records nothing: what it kept from finishing may concern any of them."""
    mine = {f.resolve() for f in files}
    if any(n.startswith("timeout:") for n in notes) or any(i.file.resolve() not in mine for i in blocking):
        return
    found = {i.file.resolve() for i in blocking} | {s.file.resolve() for s in hints}
    for repo, group in by_repo(files).items():
        record(repo, [f for f in group if f.resolve() not in found])


def accept_command(repos: Iterable[Path], cwd: Path) -> str:
    """The command that accepts what was blocked in `repos`, as the block messages offer it: `broom known --accept
    "<why>"` in backticks, with the repo's path where `cwd` isn't the repo. One command for each repo."""
    return " and ".join("`" + 'broom known --accept "<why>"' + ("" if r == cwd else f" {shlex.quote(str(r))}") + "`"
                        for r in repos)


def issues_by_repo(issues: List[Issue]) -> Dict[Path, List[Issue]]:
    """`issues` grouped by the repo their file is in; an issue outside any repo is left out."""
    groups: Dict[Path, List[Issue]] = {}
    for i in issues:
        root = git_root(i.file.parent)
        if root:
            groups.setdefault(root, []).append(i)
    return groups


def block_head(count: int, repo: Path, cwd: Path) -> str:
    """The first lines of a commit's denial: what to do about the findings, fix them or accept them with a reason."""
    head = f"[broom] Commit blocked: {count} issue(s) in the files being committed. Fix them and commit again"
    if not accept_allowed():
        return f"{head}; accepting them is off here (BROOM_NO_ACCEPT)."
    return (f"{head}. If one predates this change or is a false positive, run {accept_command([repo], cwd)}, then "
            "commit again.")


def entries_of(issues: Iterable[Issue]) -> Dict[str, dict]:
    """Each finding in `issues` by its key (gate.issue_key), with its entry (gate.issue_entry): the form the ledger and
    the gate's stored `blocked` state take."""
    return {issue_key(i): issue_entry(i) for i in issues}


def skip_context(sd: Path, notes: List[str], repo: Path) -> List[str]:
    """What Claude is told about the tools that didn't run, once per session."""
    fresh = new_notes(sd / "notes.json", notes, repo)
    if not fresh:
        return []
    hint = setup_hint(fresh)
    return ["broom skipped: " + "; ".join(note_text(n) for n in fresh)] + ([hint] if hint else [])


def gate_files(repo: Path, files: List[Path], sd: Path, cwd: Path, state: dict) -> Tuple[Optional[str], List[str]]:
    """Check what a commit takes from `repo`: the denial when it must stop (else None), and lines of context.
    `state` holds each repo's last blocked commit, for `broom known --accept` and the ledger: what it found, which
    hook and which turn saw it."""
    files = sorted(f for f in files if lang_of(f))
    blocking, hints, notes = checked(files)
    context = [hint_text(hints)] if hints else []
    ledger.hinted(entries_of(s.issue() for s in hints))
    key = str(repo)
    found = entries_of(blocking)
    prior = state.get(key, {})
    if prior.get("pending"):
        ledger.fixes(prior["pending"], found, baseline_keys(), files, notes)
    if not blocking:
        state.pop(key, None)
        return None, context + skip_context(sd, notes, repo)
    ledger.blocked(found)
    state[key] = {"pending": found, "where": ledger.HOOK.where, "turn": str(sd)}
    head = block_head(len(blocking), repo, cwd)
    return render(head, blocking, new_notes(sd / "notes.json", notes, repo), set(files)), context


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
    save_commits(state, [repo])
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
    plans = commit_plans(ops)
    for plan in plans:
        if setting("format_on", plan.repo) != "off":
            context += format_commit(plan)
        if setting("check_on", plan.repo) == "off" or installed(plan.repo):
            continue  # with git's hook here, the check is its: it sees what the commit really takes
        denial, more = gate_files(plan.repo, list(plan.files), sd, cwd, state)
        context += more
        denials += [denial] if denial else []
    save_commits(state, {plan.repo for plan in plans})
    answer(denials, context)
