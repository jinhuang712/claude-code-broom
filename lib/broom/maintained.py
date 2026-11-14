"""Which of a repo's paths hold code someone here maintains, decided by directory name before any file is read.

Dependencies and environments are left out wherever they are, and so is generated code. A few names (`build`,
`out`, `release`, `target`) are build output in some projects and source in others: files under them are left out
only where git doesn't track them. Tracked files left out by name are reported, so a skipped directory is never a
silent one.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

from .common import git

# Dependencies, environments and build output nobody here maintains: never read, not even for what uses what.
DEPENDENCY_DIRS = {
    "node_modules", "vendor", "Pods", "Carthage", ".venv", "venv", "site-packages", "__pycache__", ".build",
    "DerivedData", "dist", ".bundle", ".next", "coverage", "test-results",
}
# Generated code and fixtures: their smells don't count, but what they use isn't dead code.
GENERATED_DIRS = {"testdata", "Generated", "generated"}
# Build output in some projects, source in others: left out only where git doesn't track the files.
OUTPUT_DIRS = {"build", "out", "release", "target"}
MINIFIED = (".min.js", ".d.ts")
NOTE_DIRS = 5


def tracked_output(repo: Path) -> Set[str]:
    """Tracked files under a directory named like build output, relative to `repo`."""
    out = git(["ls-files", "-z", "--cached", "--", *(f":(glob)**/{d}/**" for d in sorted(OUTPUT_DIRS))], repo)
    return {f for f in (out or "").split("\0") if f}


class Maintained:
    """Call it with a path relative to the repo: whether someone here maintains the code there."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.tracked = tracked_output(repo)
        self.skipped: Set[str] = set()  # the directories left out by name, as `record` saw them

    def skipped_dir(self, rel: str) -> Optional[str]:
        """The directory `rel` is left out for, by its name, or None."""
        parts = rel.split("/")[:-1]
        for i, part in enumerate(parts):
            if part in DEPENDENCY_DIRS or part in GENERATED_DIRS or (part in OUTPUT_DIRS and rel not in self.tracked):
                return "/".join(parts[: i + 1])
        return None

    def __call__(self, rel: str) -> bool:
        return self.skipped_dir(rel) is None and not rel.endswith(MINIFIED)

    def record(self, rel: str) -> bool:
        """Like a call, and remembers the directory a path was left out for, for `note`."""
        where = self.skipped_dir(rel)
        if where:
            self.skipped.add(where)
        return self(rel)

    def dead_code_skips(self) -> List[str]:
        """Directory names jscpd leaves out when it looks for dead code; it skips what .gitignore does on its own.
        An output-like name stays in where git tracks files under it, and generated code stays in: what it uses is
        used."""
        in_use = {part for rel in self.tracked for part in rel.split("/")[:-1]} & OUTPUT_DIRS
        return sorted(DEPENDENCY_DIRS | (OUTPUT_DIRS - in_use))

    def clone_skips(self) -> List[str]:
        """Directory names jscpd leaves out when it looks for duplicates: generated code too, as nobody edits it."""
        return sorted(set(self.dead_code_skips()) | GENERATED_DIRS)

    def note(self) -> Optional[str]:
        """The directories left out by name that git tracks files in: maybe someone's code after all."""
        if not self.skipped:
            return None
        out = git(["--literal-pathspecs", "ls-files", "-z", "--cached", "--", *sorted(self.skipped)], self.repo)
        dirs = sorted({self.skipped_dir(f) for f in (out or "").split("\0") if f} & self.skipped)
        if not dirs:
            return None
        more = f" and {len(dirs) - NOTE_DIRS} more" if len(dirs) > NOTE_DIRS else ""
        return ("tracked directories taken for dependencies or generated code, so not measured: "
                + ", ".join(f"{d}/" for d in dirs[:NOTE_DIRS]) + more)
