"""Running commands and asking git: the repo root, what changed and since when, what git sees as renamed, and
which lines of a file differ from a base."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

HOOK_SECONDS = 25  # all one hook run may take; Claude Code ends a hook at 30 (hooks.json), and waits for it until then


THREAD_VARS = ("GOMAXPROCS", "RAYON_NUM_THREADS", "CARGO_BUILD_JOBS")  # Go, Rust's rayon (oxlint, jscpd), cargo


class Clock:
    """What one hook run lends the commands it starts: the time left between them, and a cap on the threads each
    may use, so a check doesn't take every core from what the person is doing meanwhile. Outside a hook
    (`broom sweep`, `broom smells`) it is never started: each command keeps its own timeout and all the cores."""

    def __init__(self) -> None:
        self.end: Optional[float] = None
        self.env: Dict[str, str] = {}

    def start(self, seconds: float) -> None:
        """Start the hook's time budget of `seconds`, and the thread caps for the commands it starts."""
        self.end = time.monotonic() + seconds
        threads = str(max(2, (os.cpu_count() or 4) // 4))
        self.env = {name: threads for name in THREAD_VARS if not os.environ.get(name)}  # the person's own win

    def left(self) -> Optional[float]:
        """Seconds left in the hook's budget, never below zero; None outside a hook, where no budget is started."""
        return None if self.end is None else max(0.0, self.end - time.monotonic())


CLOCK = Clock()


def kill_group(p: "subprocess.Popen[bytes]") -> None:
    """End a command and what it started: a linter's own compiler keeps the CPU busy after the linter is gone."""
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        p.kill()


# What every command broom starts gets, in a hook or not: git doesn't wait on a prompt, doesn't take the optional
# index lock a read refreshes it with (the agents and the person run git meanwhile), and doesn't start the file
# system monitor daemon, which lives on holding the pipes of the command that started it.
QUIET_ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
NO_FSMONITOR = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": "false"}


def command_env(env: Optional[Dict[str, str]]) -> Dict[str, str]:
    """The environment for a command: the process's own, plus broom's quiet settings, thread caps and `env`."""
    quiet = {} if "GIT_CONFIG_COUNT" in os.environ else NO_FSMONITOR  # the person's own config count wins
    return {**os.environ, **QUIET_ENV, **quiet, **CLOCK.env, **(env or {})}


def reap(p: "subprocess.Popen[bytes]") -> None:
    """Wait up to 2 seconds for process `p` after a kill; if it still hasn't exited, give up without an error."""
    try:
        p.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass  # in a state a kill doesn't reach: it is not waited for


def run_bytes(cmd: List[str], cwd: Path, timeout: float = 90, env: Optional[Dict[str, str]] = None,
              stdin: Optional[bytes] = None) -> Tuple[Optional[int], bytes, bytes]:
    """Run a command, and give back what it wrote. The return code is None when it timed out, or when the hook's time
    (CLOCK) was used up before or while it ran; -1 when it couldn't start. `env` adds to the environment.

    The command writes to files, not pipes, and reads `stdin` from a file or from nothing. A pipe is open as long as
    any process holds the end of it, so a command that exited, leaving a daemon it started (a language server, a
    file system monitor, a build server), kept the caller waiting for the daemon, up to the command's timeout, and
    after a timeout for good. A file is read when the command is done."""
    left = CLOCK.left()
    if left is not None:
        if left <= 0:
            return None, b"", b""
        timeout = min(timeout, left)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as given:
        if stdin is not None:
            given.write(stdin)
            given.seek(0)
        try:
            p = subprocess.Popen(cmd, cwd=str(cwd), stdin=given if stdin is not None else subprocess.DEVNULL,
                                 stdout=out, stderr=err, env=command_env(env), start_new_session=True)
        except OSError as e:
            return -1, b"", str(e).encode()
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_group(p)
            reap(p)
            return None, b"", b""
        except BaseException:  # Ctrl-C or the like: its own session no longer gets the signal from the terminal
            kill_group(p)
            raise
        out.seek(0)
        err.seek(0)
        return rc, out.read(), err.read()


def run(cmd: List[str], cwd: Path, timeout: float = 90,
        env: Optional[Dict[str, str]] = None) -> Tuple[Optional[int], str, str]:
    """`run_bytes`, with the output as text."""
    rc, out, err = run_bytes(cmd, cwd, timeout, env)
    return rc, out.decode(errors="replace"), err.decode(errors="replace")


def git(args: List[str], cwd: Path) -> Optional[str]:
    """The stdout of `git args` run in `cwd` as text, or None when git fails or times out. File names come as they
    are: left to itself git quotes and escapes a name with a non-ASCII character, and no file has that name."""
    rc, out, _ = run(["git", "-c", "core.quotePath=false", *args], cwd, timeout=15)
    return out if rc == 0 else None


_git_roots: Dict[Path, Optional[Path]] = {}


def toplevel(d: Path) -> Optional[Path]:
    """The top of the work tree git finds when it runs in `d`, or None when it finds none."""
    out = git(["rev-parse", "--show-toplevel"], d)
    return Path(out.strip()).resolve() if out and out.strip() else None


def asked_root(d: Path) -> Optional[Path]:
    """The repo `d` is in, when the environment points git somewhere (GIT_DIR, GIT_WORK_TREE), asked of git where
    the process runs, as git's own hook runs it: in the top of the work tree. Without a GIT_WORK_TREE git takes the
    directory it runs in for that top, and a GIT_WORK_TREE of `.` (what `--work-tree` hands a hook) names it, so
    asked in a folder below, git would call that folder the top and every file in it new. A folder outside that
    top is asked about itself."""
    if not d.is_dir():
        return None
    start = Path.cwd().resolve()
    if start not in _git_roots:
        _git_roots[start] = toplevel(start)
    top = _git_roots[start]
    return top if top and d.resolve().is_relative_to(top) else toplevel(d)


def git_root(d: Path) -> Optional[Path]:
    """The repo `d` is in: the nearest directory above it with a `.git`, without starting git, which a check asks
    once per directory of every file it looks at. With GIT_DIR or GIT_WORK_TREE set, git is asked (asked_root)."""
    if d not in _git_roots:
        if os.environ.get("GIT_DIR") or os.environ.get("GIT_WORK_TREE"):
            _git_roots[d] = asked_root(d)
        else:
            here = d.resolve() if d.is_dir() else None
            _git_roots[d] = next((p for p in (here, *here.parents) if (p / ".git").exists()), None) if here else None
    return _git_roots[d]


_main_roots: Dict[Path, Path] = {}


def shared_git_dir(root: Path) -> Optional[Path]:
    """The git directory the worktree at `root` shares with its main checkout, read from git's own files without
    starting git: `.git` itself in a main checkout; from a linked worktree, where `.git` is a file that names the
    worktree's own git directory, what the `commondir` file there points to. None when the files don't say (a
    submodule has no `commondir`), or when the environment names a git directory of its own."""
    if os.environ.get("GIT_DIR") or os.environ.get("GIT_COMMON_DIR"):
        return None
    dot = root / ".git"
    if dot.is_dir():
        return dot.resolve()
    try:
        own = root / dot.read_text().split("gitdir:", 1)[1].strip()  # an absolute path stays as it is
        return (own / (own / "commondir").read_text().strip()).resolve()
    except (OSError, IndexError):
        return None


def main_worktree(root: Path) -> Path:
    """The root of the main worktree of the repo whose worktree root is `root`: `root` itself in the main checkout,
    the main checkout from a linked worktree (they share the git common directory). Asked once per root and
    process; git is started only where its files don't say (see shared_git_dir)."""
    if root not in _main_roots:
        shared = shared_git_dir(root)
        if shared is None:
            common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], root)
            shared = Path(common.strip()).resolve() if common and common.strip() else None
        _main_roots[root] = shared.parent if shared and shared.name == ".git" else root
    return _main_roots[root]


# What comes before the path in an entry of `git status --porcelain=v2`, by the entry's first field: a changed
# file (1), an unmerged one (u), an untracked one (?). A rename (2) is never listed: the call turns renames off.
STATUS_FIELDS = {"1": 7, "u": 9, "?": 0}


def tree_state(root: Path) -> Tuple[str, List[Path]]:
    """HEAD's commit ("" before the first one) and the files that differ from it: tracked files changed in the index
    or the working tree, plus untracked, non-ignored files. One `git status` says all of it, where a `rev-parse`, a
    `diff` and an `ls-files` each cost a start of git; a turn's end with nothing to check pays for this call alone."""
    out = git(["status", "--porcelain=v2", "--branch", "-z", "--no-renames", "--untracked-files=all"], root) or ""
    head, names = "", []
    for entry in out.split("\0"):
        kind, _, rest = entry.partition(" ")
        if kind == "#" and rest.startswith("branch.oid "):
            head = rest.split(" ", 1)[1].replace("(initial)", "")
        elif kind in STATUS_FIELDS:
            names.append(rest.split(" ", STATUS_FIELDS[kind])[-1])
    return head, [p for p in ((root / n).resolve() for n in names if n) if p.is_file()]


def git_changed_files(root: Path) -> List[Path]:
    """Tracked files changed against HEAD plus untracked, non-ignored files."""
    return tree_state(root)[1]


def ignored(files: List[Path]) -> Set[Path]:
    """The `files` git ignores (`.gitignore`, `.git/info/exclude`, the global ignore file), a tracked one never: one
    `git check-ignore` for all the files of a repo. A file outside a repo, or a call that fails, ignores nothing."""
    by_repo: Dict[Path, List[Path]] = {}
    for f in files:
        root = git_root(f.parent)
        if root:
            by_repo.setdefault(root, []).append(f)
    out: Set[Path] = set()
    for root, group in by_repo.items():
        named = git(["check-ignore", "--", *map(str, group)], root) or ""  # None: none is ignored, or git failed
        out |= {Path(n) for n in named.splitlines() if n}
    return out


def changed_since(root: Path, base: str) -> Optional[List[Path]]:
    """Files changed since `base`, a renamed one under its new name, plus untracked, non-ignored files; None for
    an unknown revision."""
    out = git(["diff", "--name-only", "--diff-filter=ACMR", base], root)
    if out is None:
        return None
    untracked = git(["ls-files", "--others", "--exclude-standard"], root) or ""
    return [(root / n).resolve() for n in (out + untracked).splitlines() if n]


def renamed(root: Path, since: List[str]) -> Dict[str, str]:
    """Files git sees as renamed (`git mv`, or a move staged with `git add`), new path to old, both relative to
    `root`. `since` is what `git diff` compares with: `[rev]` for the working tree, `["--cached", rev]` the index."""
    parts = (git(["diff", "-M", "--diff-filter=R", "--name-status", "-z", *since], root) or "").split("\0")
    return {parts[i + 2]: parts[i + 1] for i in range(0, len(parts) - 2, 3) if parts[i].startswith("R")}


class ChangedLines:
    """Line numbers of each file that differ from `base` (the index against HEAD when `cached`); None means
    every line counts. A renamed file is compared with its old path, so moving a file changes none of its lines."""

    HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    def __init__(self, base: str = "HEAD", *, cached: bool = False) -> None:
        self.base = base
        self.cached = cached
        self._cache: Dict[Path, Optional[Set[int]]] = {}
        self._repos: Dict[Path, Optional[Tuple[Set[str], Set[str]]]] = {}
        self._renames: Dict[Path, Dict[str, str]] = {}

    def old_path(self, f: Path, root: Path) -> Optional[Path]:
        """The path `f` had before a rename in the diff against the base, or None when it was not renamed."""
        if root not in self._renames:
            self._renames[root] = renamed(root, (["--cached"] if self.cached else []) + [self.base])
        try:
            old = self._renames[root].get(f.resolve().relative_to(root).as_posix())
        except ValueError:
            return None
        return root / old if old else None

    def get(self, f: Path) -> Optional[Set[int]]:
        """The line numbers of `f` changed since the base, cached per file; None when git can't say (e.g. untracked)."""
        if f not in self._cache:
            self._cache[f] = self._compute(f)
        return self._cache[f]

    def forget(self, f: Path) -> None:
        """Ask again about `f`, a file rewritten (by a formatter) since it was asked about. What git said of the repo
        and of the tracked files stays, which spares the calls that cost most: `f` is taken for a file that differs
        from the base, so its own diff is read, which says the truth either way."""
        self._cache.pop(f, None)
        self._renames.clear()
        root = git_root(f.parent)
        repo = self._repos.get(root) if root else None
        if root and repo:
            try:
                repo[1].add((f.parent.resolve() / f.name).relative_to(root).as_posix())
            except ValueError:
                pass  # outside the repo's work tree: it was never asked about

    def _repo(self, root: Path) -> Optional[Tuple[Set[str], Set[str]]]:
        """The files git tracks in `root` and those that differ from the base, each asked of git once, not once per
        file; None when the base isn't a revision there."""
        if root not in self._repos:
            from concurrent.futures import ThreadPoolExecutor  # only where git is asked: a hook that asks nothing skips it

            mode = ["--cached"] if self.cached else []
            asks = [["rev-parse", "--verify", "-q", self.base], ["ls-files", "-z"],
                    ["diff", "--name-only", "-z", "-M", *mode, self.base]]
            with ThreadPoolExecutor(max_workers=len(asks)) as pool:  # three processes at once, not one after another
                base, tracked, differ = pool.map(lambda args: git(args, root), asks)
            self._repos[root] = None if base is None else (set((tracked or "").split("\0")),
                                                           set((differ or "").split("\0")))
        return self._repos[root]

    def _compute(self, f: Path) -> Optional[Set[int]]:
        root = git_root(f.parent)
        repo = self._repo(root) if root else None
        if root is None or repo is None:
            return None
        try:
            rel = (f.parent.resolve() / f.name).relative_to(root).as_posix()
        except ValueError:
            return None
        tracked, differ = repo
        if rel not in tracked:
            return None  # untracked: all of it is new
        if rel not in differ:
            return set()  # tracked and the same as the base: no line is new
        mode = ["--cached"] if self.cached else []
        old = self.old_path(f, root)
        paths = [str(f)] + ([str(old)] if old else [])
        out = git(["diff", "-U0", "-M", "--no-color", "--no-ext-diff", *mode, self.base, "--", *paths], root) or ""
        lines: Set[int] = set()
        for row in out.splitlines():
            m = self.HUNK.match(row)
            if not m:
                continue
            start, count = int(m.group(1)), int(m.group(2) or 1)
            lines.update({start, start + 1} if count == 0 else range(start, start + count))
        return lines
