"""The commit gate: what stops a commit, for Claude Code's commit hook (PreToolUse on a Bash `git commit`) and for
git's own pre-commit hook, which `broom install-hook` adds for commits that hook never sees. The turn-end gate
checks with the same `checked`.

Every finding that stops, lint included and a smell's hint with a smell's block, passes fixed, or after Claude
accepts it with `broom known --accept "<why>"`, which puts the reason on record: a retry alone lets nothing through.
A false positive or a refactor that comes in a later step costs one command, and Claude tells the user what it
accepted. Where the user must decide, `broom known --ask "<question>"` and then stopping puts the question to them: it
passes nothing. A nit, a slight smell, is told and stops nothing.
"""

from __future__ import annotations

import os
import re
import shlex
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from . import ledger, waivers
from .checks import SLOW_PATH, run_checks
from .findings import Issue
from .config import excluded, setting
from .fmt import format_files
from .gate import (
    COMMITS, accept_allowed, baseline_keys, issue_entry, issue_key, kept_blocks, last_block, new_notes, note_text,
    open_findings, render, save_commits, select, setup_hint,
)
from .gitcmd import CommitPlan, GitOp, parse, parse_commit, plan_commit, staged
from .githook import installed
from .gitutil import ChangedLines, git, git_root
from .passed import record, staged_blobs, unpassed, worktree_blobs
from .smells import Smell, gate_smells, nits_text
from .state import DATA_ROOT, emit, load_json, session_dir, warn
from .toolchain import lang_of


ACCEPT_FLAG = '--accept "<why>"'  # how a block message writes the commands it offers
ASK_FLAG = '--ask "<what they must decide, and why>"'


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
    """Group `files` by the git repo each one is in (its root), leaving out files outside any repo."""
    groups: Dict[Path, List[Path]] = {}
    for f in files:
        root = git_root(f.parent)
        if root:
            groups.setdefault(root, []).append(f)
    return groups


def checked(files: List[Path], base: str = "HEAD", turn: Optional[Path] = None
            ) -> Tuple[List[Issue], List[Smell], List[str]]:
    """What stops (lint and type issues not yet known, smells past a limit: blocks and hints), the smell notes that
    are only told, and the tool notes, for what changed since `base`. Content that passed before isn't checked
    again; content that passes now is recorded. What the change loosens (a suppression it adds, a looser
    .broom.json) is noted for `turn`, the directory of the turn it belongs to."""
    files = [f for repo, group in by_repo(files).items() for f in unpassed(repo, group, worktree_blobs(repo, group))]
    if not files:
        return [], [], []
    issues, notes = run_checks(files, SLOW_PATH)
    known = baseline_keys()
    changed, groups = ChangedLines(base), by_repo(files)
    blocking = select(issues, set(files), known, changed)
    told: List[Smell] = []
    for repo, group in groups.items():
        smell_stops, smell_told, smell_notes = gate_smells(repo, group, known, base)
        blocking += smell_stops
        told += smell_told
        notes += smell_notes
    ledger.waived(waivers.detect(groups, changed, base), turn)
    record_passed(files, blocking, told, notes)
    return blocking, told, notes


def record_passed(files: List[Path], blocking: List[Issue], told: List[Smell], notes: List[str]) -> None:
    """Record each file nothing stopped and nothing noted, so one file with a finding doesn't make the rest run
    again at the next try. A timeout, or a finding outside these files (a type error in a file they affect),
    records nothing: what it kept from finishing may concern any of them."""
    mine = {f.resolve() for f in files}
    if any(n.startswith("timeout:") for n in notes) or any(i.file.resolve() not in mine for i in blocking):
        return
    found = {i.file.resolve() for i in blocking} | {s.file.resolve() for s in told}
    for repo, group in by_repo(files).items():
        record(repo, [f for f in group if f.resolve() not in found])


def known_command(repos: Iterable[Path], cwd: Path, flag: str) -> str:
    """The `broom known` command with `flag` (such as `--accept "<why>"`) in backticks, as the block messages offer it,
    with the repo's path where `cwd` isn't the repo. One command for each repo."""
    return " and ".join("`" + f"broom known {flag}" + ("" if r == cwd else f" {shlex.quote(str(r))}") + "`"
                        for r in repos)


def issues_by_repo(issues: List[Issue]) -> Dict[Path, List[Issue]]:
    """`issues` grouped by the repo their file is in; an issue outside any repo is left out."""
    groups: Dict[Path, List[Issue]] = {}
    for i in issues:
        root = git_root(i.file.parent)
        if root:
            groups.setdefault(root, []).append(i)
    return groups


def block_head(count: int) -> str:
    """The first line of a commit's denial: what was blocked, and the first thing to do about it."""
    return f"[broom] Commit blocked: {count} issue(s) in the files being committed. Fix them and commit again."


def way_out(repos: Iterable[Path], cwd: Path, then: str) -> str:
    """The last of a block's own lines: that trying again passes nothing, and how a finding passes then: fixed, or
    accepted with a reason (said to the user) and then doing `then` (`commit again`, `stop again`); or put to the user,
    who decides, by `broom known --ask` and stopping. Where accepting is off, only a fix passes, or the user's answer."""
    repos = list(repos)
    ask = (f"If the user must decide, run {known_command(repos, cwd, ASK_FLAG)} and then stop: that puts the question "
           "to them.")
    if not accept_allowed():
        return ("Trying again passes nothing. Fixing is the only way out: accepting them is off here (BROOM_NO_ACCEPT).\n"
                + ask)
    return "\n".join([
        "Trying again passes nothing: only a fix does, or accepting with a reason.",
        f"Accept only for a real reason, such as a false positive or a refactor that comes in a later step: run "
        f"{known_command(repos, cwd, ACCEPT_FLAG)}, then {then}. Say in your reply to the user what you accepted and "
        "why.",
        f"{ask} Add --agreed to --accept only when the user said yes.",
    ])


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
    hook and which turn saw it. What an earlier commit blocked in files this one didn't take stays in it, for the
    commit that does."""
    files = sorted(f for f in files if lang_of(f))
    blocking, told, notes = checked(files, turn=sd)
    context = [nits_text(told)] if told else []
    ledger.hinted(entries_of(s.issue() for s in told))
    key, found, known = str(repo), entries_of(blocking), baseline_keys()
    prior = open_findings(state.get(key, {}))
    ended = ledger.fixes(prior, found, known, files, notes) if prior else set()
    kept = kept_blocks(state.get(key), known, {*found, *ended})
    if blocking or kept:
        state[key] = last_block(found, kept, sd)
    else:
        state.pop(key, None)
    if not blocking:
        return None, context + skip_context(sd, notes, repo)
    ledger.blocked(found)
    return render(block_head(len(blocking)), blocking, new_notes(sd / "notes.json", notes, repo), set(files),
                  way_out([repo], cwd, "commit again")), context


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
        warn(line)
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
    """Emit the PreToolUse answer: a deny with its reasons, else the context as a note; nothing if neither."""
    out: dict = {"hookEventName": "PreToolUse"}
    if denials:
        out["permissionDecision"] = "deny"
        out["permissionDecisionReason"] = "\n\n".join(denials + context)
    elif context:
        # A note carries lines of its own (how to fix): they go on separate lines, not run on after a semicolon.
        out["additionalContext"] = ("\n" if any("\n" in c for c in context) else "; ").join(context)
    if len(out) > 1:
        emit({"hookSpecificOutput": out})


def hook_commit(data: dict) -> bool:
    """Claude Code's PreToolUse hook on Bash: format and check what each `git commit` in the command takes. True when it
    denied the command, which then never runs."""
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    ops = parse((data.get("tool_input") or {}).get("command") or "", cwd)
    if not any(op.kind == "commit" for op in ops) or not claim(data.get("tool_use_id")):
        return False
    sd = session_dir(data.get("session_id") or "cli")
    ledger.waived(waivers.no_verify_waivers(ops, (data.get("tool_input") or {}).get("command") or ""), sd)
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
    return bool(denials)
