"""What content a test run tested, and which of a turn's files that content covers (F2.13).

When a test run starts it notes, for the repo it runs in, HEAD's commit and the blob id of each code file that differs
from HEAD or is untracked, as the file is on disk. A file that equals HEAD is the blob HEAD has, so it needs no row;
a repo with no commit yet has every code file in the rows. At a turn's end a file the turn changed is covered by a run
when its blob now is the one the run tested. That is judged by content and never by modification time: work tested in
a linked worktree and then merged into the main checkout, a file only touched, a formatter that rewrites nothing and a
file restored to what was tested all count as tested. The worktrees of one repo share their objects and their paths
below the root, so a run in one covers the same blob at the same path in another.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

from .config import REPO_FILE
from .gitutil import git, main_worktree
from .passed import worktree_blobs
from .turns import tree


def snapshot(root: Path) -> dict:
    """What a test run in the work tree at `root` tests: the repo it belongs to (`main`, the root of its main worktree),
    HEAD's commit (`head`, "" before the first) and the blob of each changed or untracked code file (`dirty`, by path)."""
    now = tree(root)
    files = [root / rel for rel in now["files"] if rel != REPO_FILE]
    return {"main": str(main_worktree(root)), "head": now["head"], "dirty": worktree_blobs(root, files)}


def blobs_at(root: Path, head: str, rels: List[str]) -> Dict[str, str]:
    """The blob id each of the paths `rels` has at the commit `head`, in one git call; a path it lacks is left out."""
    out = (git(["ls-tree", "-r", "-z", head, "--", *rels], root) or "") if head and rels else ""
    rows = (row.split("\t", 1) for row in out.split("\0") if "\t" in row)
    return {path: meta.split()[2] for meta, path in rows}


def covered(run: dict, current: Dict[str, str], at_head: Dict[str, str]) -> Set[str]:
    """The paths of `current` (path to blob now) whose content the `run` tested: the blob it noted for the path if it
    noted one, else the one its HEAD (`at_head`) has."""
    dirty = run.get("dirty") or {}
    return {rel for rel, blob in current.items() if (dirty[rel] if rel in dirty else at_head.get(rel)) == blob}


def coverage(root: Path, runs: List[dict], current: Dict[str, str]) -> List[Set[str]]:
    """For each of `runs` the paths of `current` it covers. The blobs at the runs' commits are read with one git call for
    each commit, run from `root`: the commit may be one of another worktree of the repo."""
    heads = {r["head"] for r in runs if r.get("head")}
    at = {head: blobs_at(root, head, list(current)) for head in heads}
    return [covered(r, current, at.get(r.get("head") or "", {})) for r in runs]
