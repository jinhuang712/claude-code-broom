"""Running commands and asking git: the repo root, what changed and since when, what git sees as renamed, and
which lines of a file differ from a base."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

def run(cmd: List[str], cwd: Path, timeout: float = 90,
        env: Optional[Dict[str, str]] = None) -> Tuple[Optional[int], str, str]:
    """Run a command; the return code is None when it timed out. `env` adds to the environment."""
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, **env} if env else None)
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return None, "", ""
    except OSError as e:
        return -1, "", str(e)


def git(args: List[str], cwd: Path) -> Optional[str]:
    rc, out, _ = run(["git", *args], cwd, timeout=15)
    return out if rc == 0 else None


_git_roots: Dict[Path, Optional[Path]] = {}


def git_root(d: Path) -> Optional[Path]:
    if d not in _git_roots:
        out = git(["rev-parse", "--show-toplevel"], d) if d.is_dir() else None
        _git_roots[d] = Path(out.strip()).resolve() if out else None
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

    def _compute(self, f: Path) -> Optional[Set[int]]:
        root = git_root(f.parent)
        if root is None or git(["rev-parse", "--verify", "-q", self.base], root) is None:
            return None
        if git(["ls-files", "--error-unmatch", str(f)], root) is None:
            return None  # untracked: all of it is new
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
