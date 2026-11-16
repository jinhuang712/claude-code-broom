"""Running commands and asking git: the repo root, what changed and since when, what git sees as renamed, and
which lines of a file differ from a base."""

from __future__ import annotations

import os
import re
import signal
import subprocess
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
        self.end = time.monotonic() + seconds
        threads = str(max(2, (os.cpu_count() or 4) // 4))
        self.env = {name: threads for name in THREAD_VARS if not os.environ.get(name)}  # the person's own win

    def left(self) -> Optional[float]:
        return None if self.end is None else max(0.0, self.end - time.monotonic())


CLOCK = Clock()


def kill_group(p: "subprocess.Popen[str]") -> None:
    """End a command and what it started: a linter's own compiler keeps the CPU busy after the linter is gone."""
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        p.kill()


def run(cmd: List[str], cwd: Path, timeout: float = 90,
        env: Optional[Dict[str, str]] = None) -> Tuple[Optional[int], str, str]:
    """Run a command; the return code is None when it timed out, or when the hook's time (CLOCK) was used up
    before or while it ran. `env` adds to the environment."""
    left = CLOCK.left()
    if left is not None:
        if left <= 0:
            return None, "", ""
        timeout = min(timeout, left)
    extra = {**CLOCK.env, **(env or {})}
    try:
        p = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env={**os.environ, **extra} if extra else None, start_new_session=True)
    except OSError as e:
        return -1, "", str(e)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(p)
        p.communicate()
        return None, "", ""
    except BaseException:  # Ctrl-C or the like: its own session no longer gets the signal from the terminal
        kill_group(p)
        raise
    return p.returncode, out or "", err or ""


def git(args: List[str], cwd: Path) -> Optional[str]:
    rc, out, _ = run(["git", *args], cwd, timeout=15)
    return out if rc == 0 else None


_git_roots: Dict[Path, Optional[Path]] = {}


def git_root(d: Path) -> Optional[Path]:
    """The repo `d` is in: the nearest directory above it with a `.git`, without starting git, which a check asks
    once per directory of every file it looks at. With GIT_DIR or GIT_WORK_TREE set, git is asked."""
    if d not in _git_roots:
        if os.environ.get("GIT_DIR") or os.environ.get("GIT_WORK_TREE"):
            out = git(["rev-parse", "--show-toplevel"], d) if d.is_dir() else None
            _git_roots[d] = Path(out.strip()).resolve() if out else None
        else:
            here = d.resolve() if d.is_dir() else None
            _git_roots[d] = next((p for p in (here, *here.parents) if (p / ".git").exists()), None) if here else None
    return _git_roots[d]


def git_changed_files(root: Path) -> List[Path]:
    """Tracked files changed against HEAD plus untracked, non-ignored files."""
    files: List[str] = []
    out = git(["diff", "--name-only", "--no-renames", "HEAD"], root)
    if out is None:  # no commits yet
        out = git(["diff", "--name-only", "--cached"], root) or ""
    files += out.splitlines()
    files += (git(["ls-files", "--others", "--exclude-standard"], root) or "").splitlines()
    return [p for p in ((root / f).resolve() for f in files if f) if p.is_file()]


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
        if root not in self._renames:
            self._renames[root] = renamed(root, (["--cached"] if self.cached else []) + [self.base])
        try:
            old = self._renames[root].get(f.resolve().relative_to(root).as_posix())
        except ValueError:
            return None
        return root / old if old else None

    def get(self, f: Path) -> Optional[Set[int]]:
        if f not in self._cache:
            self._cache[f] = self._compute(f)
        return self._cache[f]

    def _repo(self, root: Path) -> Optional[Tuple[Set[str], Set[str]]]:
        """The files git tracks in `root` and those that differ from the base, each asked of git once, not once per
        file; None when the base isn't a revision there."""
        if root not in self._repos:
            mode = ["--cached"] if self.cached else []
            if git(["rev-parse", "--verify", "-q", self.base], root) is None:
                self._repos[root] = None
            else:
                tracked = (git(["ls-files", "-z"], root) or "").split("\0")
                differ = (git(["diff", "--name-only", "-z", "-M", *mode, self.base], root) or "").split("\0")
                self._repos[root] = (set(tracked), set(differ))
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
