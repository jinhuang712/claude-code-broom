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
from typing import Dict, List, Optional, Set, Tuple

from .gitutil import git, git_root

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
    """One git command in a Bash line: its kind (`add` or `commit`), the directory it runs in, and its arguments."""
    kind: str  # "add" or "commit"
    cwd: Path
    args: List[str]


@dataclass
class CommitSpec:
    """What a `git commit` asks for: its directory, the -a, --no-verify and --dry-run flags, and any pathspecs."""
    cwd: Path
    all: bool = False
    no_verify: bool = False
    dry_run: bool = False
    pathspecs: List[str] = field(default_factory=list)


@dataclass
class CommitPlan:
    """The files a commit will contain, with the ones to re-add after formatting and the ones staged in part."""
    repo: Path
    files: Set[Path]  # what the commit will contain
    restage: Set[Path]  # staged in full and not re-added by the command: re-add after formatting
    partial: Set[Path]  # staged in part: formatting and re-adding would commit the unstaged hunks too


def split_commands(command: str) -> List[List[str]]:
    """Split a shell line at ; & | ( ) and newlines into one word list per command; quotes keep words whole."""
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


HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")  # <<EOF, <<-EOF, <<'EOF'; not <<<


def without_heredocs(command: str) -> str:
    """The command without the bodies of its here-documents. A body is input for a command, such as a commit's
    message: it holds no command of its own, and an apostrophe in it is no quote. Read as shell, a body with one
    made the whole line unreadable, and a `git add` before the commit went unseen. A here-document that never ends
    is left as it is."""
    kept: List[str] = []
    ends: List[Tuple[str, bool]] = []  # the end word of each here-document still open, and whether tabs lead it
    for line in command.split("\n"):
        if ends:
            word, tabs = ends[0]
            if (line.lstrip("\t") if tabs else line) == word:
                ends.pop(0)
            continue
        kept.append(line)
        ends = [(m[3], bool(m[1])) for m in HEREDOC.finditer(line)]
    return command if ends else "\n".join(kept)


REDIRECTION = re.compile(r"^\d*(?:>>?|<<?<?|<>|>\|)(\S*)$")  # > >> < << <<< <> >|, after a file descriptor or not


def without_redirections(toks: List[str]) -> List[str]:
    """A command's words without its redirections: `> file`, `2>/dev/null`, `<<EOF`, the `2>` that `2>&1` leaves
    once `&` has ended the command. They name no path the command takes. Read as words, they made
    `git commit -m x 2>&1 | tail` a commit of the path `2>`, which no changed file matched, so nothing was checked."""
    out: List[str] = []
    target_next = False
    for tok in toks:
        found = None if target_next else REDIRECTION.match(tok)
        if target_next:
            target_next = False
        elif found:
            target_next = not found[1]  # `> file`: the file is the next word
        else:
            out.append(tok)
    return out


def _commit_in_unquotable(command: str, cwd: Path) -> List[GitOp]:
    """A command shlex can't follow, such as an unquoted heredoc: read the commit's flags up to any quote."""
    m = re.search(r"\bgit\b[^\n;&|]*?\bcommit\b(?P<rest>[^\n;&|'\"]*)", command)
    return [GitOp("commit", cwd, re.findall(r"(?<!\S)-{1,2}[A-Za-z][\w-]*", m["rest"]))] if m else []


def _git_op(toks: List[str], here: Path) -> Optional[GitOp]:
    """The `git add` or `git commit` a git command is, with the directory its `-C` options point it at."""
    i, gdir = 1, here
    while i < len(toks) and toks[i].startswith("-"):
        if toks[i] == "-C" and i + 1 < len(toks):
            gdir = (gdir / os.path.expanduser(toks[i + 1])).resolve()
        i += 2 if toks[i] in GIT_GLOBAL_VALUE else 1
    if i < len(toks) and toks[i] in ("add", "commit"):
        return GitOp(toks[i], gdir, toks[i + 1:])
    return None


class _Shell:
    """What the commands of a line have set for the ones after them: the directory and the variables."""

    def __init__(self, cwd: Path):
        self.here = cwd
        # Variables the command sets for itself (`T=~/repo; git -C $T commit`); anything else comes from the
        # environment the hook runs in, which is the one the Bash tool started from.
        self.names: Dict[str, str] = {}

    def expand(self, tok: str) -> str:
        return VAR_REF.sub(lambda m: self.names.get(m[1] or m[2], os.environ.get(m[1] or m[2], m[0])), tok)

    def assigns(self, toks: List[str]) -> bool:
        """A statement of its own that sets variables (`T=~/repo`): take them. False for any other command."""
        if not toks or not all(ASSIGNMENT.match(t) for t in toks):
            return False
        for t in toks:
            name, value = ASSIGNMENT.match(t).groups()  # type: ignore[union-attr]
            self.names[name] = self.expand(value)
        return True

    def words(self, toks: List[str]) -> List[str]:
        """A command's words, expanded, without the assignments set for it alone and the wrappers before it."""
        toks = without_redirections([self.expand(t) for t in toks])
        while toks and ASSIGNMENT.match(toks[0]):  # set for one command only, after its arguments are expanded
            toks = toks[1:]
        while toks and toks[0] in WRAPPERS:
            toks = toks[1:]
        return toks

    def run(self, toks: List[str]) -> Optional[GitOp]:
        """Take one command: note what it sets, and return the git add or commit it makes, if it makes one."""
        if toks[0] == "export":
            toks = toks[1:]
        if self.assigns(toks):
            return None
        toks = self.words(toks)
        if not toks:
            return None
        if toks[0] == "cd" and len(toks) > 1:
            self.here = (self.here / os.path.expanduser(toks[1])).resolve()
            return None
        return _git_op(toks, self.here) if Path(toks[0]).name == "git" else None


def parse(command: str, cwd: Path) -> List[GitOp]:
    """The `git add` and `git commit` invocations in a shell command, in order, with the directory each runs in."""
    try:
        commands = split_commands(without_heredocs(command))
    except ValueError:
        return _commit_in_unquotable(command, cwd)
    shell = _Shell(cwd)
    return [op for op in (shell.run(toks) for toks in commands) if op]


def _short_flags(cluster: str, spec: CommitSpec) -> bool:
    """Read a cluster of short options such as `-am`; True when its last one takes the next argument as its value."""
    for j, c in enumerate(cluster[1:]):
        spec.all |= c == "a"
        spec.no_verify |= c == "n"
        if c in COMMIT_SHORT_VALUE:
            return j == len(cluster) - 2
    return False


def parse_commit(op: GitOp) -> CommitSpec:
    """Read a `git commit`'s flags (-a, --no-verify, --dry-run) and its pathspecs, the words that aren't flags."""
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
        elif _short_flags(a, spec):
            i += 1
        i += 1
    return spec


def _names(repo: Path, args: List[str]) -> Set[Path]:
    out = git(args, repo) or ""
    return {(repo / n).resolve() for n in out.splitlines() if n}


def tracked_changes(repo: Path) -> Set[Path]:
    """The tracked files with unstaged changes in `repo`, as absolute paths."""
    return _names(repo, ["diff", "--name-only", "--diff-filter=ACMR"])


def untracked(repo: Path) -> Set[Path]:
    """The files in `repo` that git neither tracks nor ignores, as absolute paths."""
    return _names(repo, ["ls-files", "--others", "--exclude-standard"])


def staged(repo: Path) -> Set[Path]:
    """The files in `repo` with staged changes (added, copied, modified or renamed), as absolute paths."""
    return _names(repo, ["diff", "--cached", "--name-only", "--diff-filter=ACMR"])


def _add_args(args: List[str]) -> Optional[Tuple[Set[str], List[str]]]:
    """The mode flags ("all", "update") and the paths of a `git add`; None when it stages nothing, or something
    only a person picks."""
    flags: Set[str] = set()
    paths: List[str] = []
    paths_only = False
    for a in args:
        if paths_only or not a.startswith("-"):
            paths.append(a)
        elif a == "--":
            paths_only = True
        elif a in ("-n", "--dry-run", "-p", "--patch", "-i", "--interactive", "-e", "--edit"):
            return None
        elif a in ("-A", "--all", "--no-ignore-removal") or (not a.startswith("--") and "A" in a):
            flags.add("all")
        elif a in ("-u", "--update") or (not a.startswith("--") and "u" in a):
            flags.add("update")
    return flags, paths


def add_targets(op: GitOp, repo: Path) -> Set[Path]:
    """Files a `git add` will stage, predicted from its arguments before it runs."""
    parsed = _add_args(op.args)
    if parsed is None:
        return set()
    flags, paths = parsed
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
    """Predict what `spec` commits, after the `adds` before it on the same line; None when not in a repo."""
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
