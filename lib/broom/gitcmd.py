"""Reading a Bash command for the git commits it makes, and working out which files each commit takes.

The PreToolUse hook runs before the command, so for `git add . && git commit` the add hasn't happened yet:
the files it will stage are predicted from its arguments.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from .common import git, git_root

COMMIT_LONG_VALUE = {
    "--message", "--file", "--reuse-message", "--reedit-message", "--author", "--date", "--template",
    "--fixup", "--squash", "--cleanup", "--trailer", "--pathspec-from-file",
}
COMMIT_SHORT_VALUE = set("mFCct")  # short options that take a value, attached or as the next argument
GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
WRAPPERS = {"command", "time", "nice", "nohup"}
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
VAR_REF = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


@dataclass
class GitOp:
    kind: str  # "add" or "commit"
    cwd: Path
    args: List[str]


@dataclass
class CommitSpec:
    cwd: Path
    all: bool = False
    no_verify: bool = False
    dry_run: bool = False
    pathspecs: List[str] = field(default_factory=list)


@dataclass
class CommitPlan:
    repo: Path
    files: Set[Path]  # what the commit will contain
    restage: Set[Path]  # staged in full and not re-added by the command: re-add after formatting
    partial: Set[Path]  # staged in part: formatting and re-adding would commit the unstaged hunks too


def split_commands(command: str) -> List[List[str]]:
    lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    cmds: List[List[str]] = []
    cur: List[str] = []
    for tok in lex:
        if tok and set(tok) <= set(";&|()\n"):
            if cur:
                cmds.append(cur)
            cur = []
        elif tok.strip():
            cur.append(tok)
    if cur:
        cmds.append(cur)
    return cmds


def parse(command: str, cwd: Path) -> List[GitOp]:
    """The `git add` and `git commit` invocations in a shell command, in order, with the directory each runs in."""
    try:
        commands = split_commands(command)
    except ValueError:  # quoting shlex can't follow, such as an unquoted heredoc: read the flags up to any quote
        m = re.search(r"\bgit\b[^\n;&|]*?\bcommit\b(?P<rest>[^\n;&|'\"]*)", command)
        return [GitOp("commit", cwd, re.findall(r"(?<!\S)-{1,2}[A-Za-z][\w-]*", m["rest"]))] if m else []
    ops: List[GitOp] = []
    here = cwd
    # Variables the command sets for itself (`T=~/repo; git -C $T commit`); anything else comes from the
    # environment the hook runs in, which is the one the Bash tool started from.
    names: Dict[str, str] = {}

    def expand(tok: str) -> str:
        return VAR_REF.sub(lambda m: names.get(m[1] or m[2], os.environ.get(m[1] or m[2], m[0])), tok)

    for toks in commands:
        if toks[0] == "export":
            toks = toks[1:]
        if toks and all(ASSIGNMENT.match(t) for t in toks):  # a statement of its own: it sets the variables
            for t in toks:
                name, value = ASSIGNMENT.match(t).groups()  # type: ignore[union-attr]
                names[name] = expand(value)
            continue
        toks = [expand(t) for t in toks]
        while toks and ASSIGNMENT.match(toks[0]):  # set for one command only, after its arguments are expanded
            toks = toks[1:]
        while toks and toks[0] in WRAPPERS:
            toks = toks[1:]
        if not toks:
            continue
        if toks[0] == "cd" and len(toks) > 1:
            here = (here / os.path.expanduser(toks[1])).resolve()
            continue
        if Path(toks[0]).name != "git":
            continue
        i, gdir = 1, here
        while i < len(toks) and toks[i].startswith("-"):
            if toks[i] == "-C" and i + 1 < len(toks):
                gdir = (gdir / os.path.expanduser(toks[i + 1])).resolve()
            i += 2 if toks[i] in GIT_GLOBAL_VALUE else 1
        if i < len(toks) and toks[i] in ("add", "commit"):
            ops.append(GitOp(toks[i], gdir, toks[i + 1:]))
    return ops


def parse_commit(op: GitOp) -> CommitSpec:
    spec = CommitSpec(op.cwd)
    args, i, paths_only = op.args, 0, False
    while i < len(args):
        a = args[i]
        if paths_only or not a.startswith("-") or a == "-":
            spec.pathspecs.append(a)
        elif a == "--":
            paths_only = True
        elif a.startswith("--"):
            name = a.split("=", 1)[0]
            spec.all |= name == "--all"
            spec.no_verify |= name == "--no-verify"
            spec.dry_run |= name == "--dry-run"
            if name in COMMIT_LONG_VALUE and "=" not in a:
                i += 1
        else:
            for j, c in enumerate(a[1:]):
                spec.all |= c == "a"
                spec.no_verify |= c == "n"
                if c in COMMIT_SHORT_VALUE:
                    if j == len(a) - 2:
                        i += 1
                    break
        i += 1
    return spec


def _names(repo: Path, args: List[str]) -> Set[Path]:
    out = git(args, repo) or ""
    return {(repo / n).resolve() for n in out.splitlines() if n}


def tracked_changes(repo: Path) -> Set[Path]:
    return _names(repo, ["diff", "--name-only", "--diff-filter=ACMR"])


def untracked(repo: Path) -> Set[Path]:
    return _names(repo, ["ls-files", "--others", "--exclude-standard"])


def staged(repo: Path) -> Set[Path]:
    return _names(repo, ["diff", "--cached", "--name-only", "--diff-filter=ACMR"])


def add_targets(op: GitOp, repo: Path) -> Set[Path]:
    """Files a `git add` will stage, predicted from its arguments before it runs."""
    flags: Set[str] = set()
    paths: List[str] = []
    paths_only = False
    for a in op.args:
        if paths_only or not a.startswith("-"):
            paths.append(a)
        elif a == "--":
            paths_only = True
        elif a in ("-n", "--dry-run", "-p", "--patch", "-i", "--interactive", "-e", "--edit"):
            return set()  # stages nothing, or something only a person picks
        elif a in ("-A", "--all", "--no-ignore-removal") or (not a.startswith("--") and "A" in a):
            flags.add("all")
        elif a in ("-u", "--update") or (not a.startswith("--") and "u" in a):
            flags.add("update")
    pool = tracked_changes(repo) | staged(repo)
    if "update" not in flags:
        pool |= untracked(repo)
    if not paths:
        return pool if flags else set()
    out: Set[Path] = set()
    for p in paths:
        if p in (":/", ":"):
            return pool
        base = (op.cwd / p).resolve()
        out |= {f for f in pool if f == base or base in f.parents}
    return out


def plan_commit(spec: CommitSpec, adds: List[GitOp]) -> Optional[CommitPlan]:
    repo = git_root(spec.cwd)
    if repo is None:
        return None
    index = staged(repo)
    unstaged = tracked_changes(repo)
    added: Set[Path] = set()
    for a in adds:
        added |= add_targets(a, repo)
    if spec.pathspecs:  # `git commit <paths>` commits those paths from the working tree
        bases = [(spec.cwd / p).resolve() for p in spec.pathspecs]
        files = {f for f in unstaged | index | added if any(f == b or b in f.parents for b in bases)}
        return CommitPlan(repo, files, set(), set())
    files = index | added | (unstaged if spec.all else set())
    reads_worktree = added | (unstaged if spec.all else set())
    partial = {f for f in index & unstaged if f not in reads_worktree}
    restage = {f for f in index - unstaged if f not in reads_worktree}
    return CommitPlan(repo, {f for f in files if f.is_file()}, restage, partial)
