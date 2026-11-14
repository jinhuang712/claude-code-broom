"""File contents that already passed the checks, by git's blob id, so the same content isn't checked twice.

A turn that edits and then commits used to check the same files at the commit and again at the turn's end, and
git's pre-commit hook would check them a third time. Content counts as passed only when nothing stopped it and
nothing hinted, and no check timed out, so a skip never hides what a check would have said. Records last a day.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List

from .common import DATA_ROOT, git, load_json, save_json

PASSED = DATA_ROOT / "passed.json"  # {repo: {path: [blob id, time]}}
KEEP_SECONDS = 86400


def rel_paths(repo: Path, files: List[Path]) -> List[str]:
    return [f.resolve().relative_to(repo).as_posix() for f in files]


def worktree_blobs(repo: Path, files: List[Path]) -> Dict[str, str]:
    """The blob id git would give each file's content as it is on disk."""
    rels = rel_paths(repo, files)
    out = (git(["hash-object", "--", *rels], repo) or "").split() if rels else []
    return dict(zip(rels, out)) if len(out) == len(rels) else {}


def staged_blobs(repo: Path, files: List[Path]) -> Dict[str, str]:
    """The blob id of each file as staged: what a commit takes."""
    rels = rel_paths(repo, files)
    out = (git(["ls-files", "-s", "-z", "--", *rels], repo) or "") if rels else ""
    rows = (row.split("\t", 1) for row in out.split("\0") if "\t" in row)
    return {path: meta.split()[1] for meta, path in rows}


def unpassed(repo: Path, files: List[Path], blobs: Dict[str, str]) -> List[Path]:
    """The files whose content, given as `blobs` (on disk or as staged), hasn't passed yet."""
    seen = load_json(PASSED, {}).get(str(repo), {})
    return [f for f, rel in zip(files, rel_paths(repo, files)) if (seen.get(rel) or [None])[0] != blobs.get(rel)]


def record(repo: Path, files: List[Path]) -> None:
    """The files' content, as it is on disk, passed."""
    if not files:
        return
    data = load_json(PASSED, {})
    cutoff = time.time() - KEEP_SECONDS
    rows = {rel: v for rel, v in data.get(str(repo), {}).items() if v[1] >= cutoff}
    now = time.time()
    rows.update({rel: [blob, now] for rel, blob in worktree_blobs(repo, files).items()})
    data[str(repo)] = rows
    save_json(PASSED, data)
