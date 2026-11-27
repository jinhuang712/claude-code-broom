"""File contents that already passed the checks, by git's blob id, so the same content isn't checked twice.

A turn that edits and then commits used to check the same files at the commit and again at the turn's end, and
git's pre-commit hook would check them a third time. Content counts as passed only when nothing stopped it and
nothing hinted, and no check timed out, so a skip never hides what a check would have said. A record stays until
what decided it changes: the content, broom's version or the repo's .broom.json. The records are kept in the repo's
folder (repodata), by worktree root; the file holds the newest MAX_ENTRIES records and drops the oldest first.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Dict, List

from . import __version__, repodata
from .config import repo_file
from .gitutil import git
from .state import load_json, update_json

# In the repo's folder, repodata.PASSED: {worktree root: {path: [blob id, written, bar]}}; `written` only orders them.
MAX_ENTRIES = 20000
RECORD_FIELDS = 3  # blob id, written, bar


def bar(repo: Path) -> str:
    """What besides a file's content decides whether it passes: broom's version and the repo's .broom.json (its
    text, or nothing when the repo has none)."""
    path = repo_file(repo)
    try:
        config = path.read_bytes() if path else b""
    except OSError:
        config = b""
    return hashlib.sha1(__version__.encode() + b"\0" + config).hexdigest()[:16]


def rel_paths(repo: Path, files: List[Path]) -> List[str]:
    """`files` as POSIX paths relative to `repo`; each file must lie under the repo."""
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
    seen = load_json(repodata.at(repo) / repodata.PASSED, {}).get(str(repo), {})
    deciding = bar(repo)
    return [f for f, rel in zip(files, rel_paths(repo, files)) if not passed(seen.get(rel), blobs.get(rel), deciding)]


def passed(record: object, blob: object, deciding: str) -> bool:
    """Whether a kept record (blob id, written, bar) is for this content under this bar; a record of the older shape,
    without a bar, is not."""
    return isinstance(record, list) and len(record) == RECORD_FIELDS and record[0] == blob and record[2] == deciding


def record(repo: Path, files: List[Path]) -> None:
    """The files' content, as it is on disk, passed."""
    if not files:
        return
    blobs = worktree_blobs(repo, files)
    now, deciding = time.time(), bar(repo)

    def add(data: dict) -> None:
        rows = data.setdefault(str(repo), {})
        rows.update({rel: [blob, now, deciding] for rel, blob in blobs.items()})
        drop_oldest(data)

    update_json(repodata.made_at(repo) / repodata.PASSED, {}, add)


def drop_oldest(data: dict) -> None:
    """Keep the newest MAX_ENTRIES records of the worktrees in `data`, in place; a worktree left with none goes."""
    rows = sorted(((v[1], repo, rel) for repo, files in data.items() for rel, v in files.items()), reverse=True)
    for _, repo, rel in rows[MAX_ENTRIES:]:
        del data[repo][rel]
    for repo in [r for r, files in data.items() if not files]:
        del data[repo]
