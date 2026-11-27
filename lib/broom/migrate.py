"""Moving a repo's records out of the data directory's old shared files, once, when broom first makes the repo's
folder (repodata). Before 0.32 every repo's records sat in shared files keyed by absolute paths.

Each old file is changed under its own lock: the repo's part is written to its folder first and only then removed from
the old file, so a crash midway loses nothing (at worst a part sits in both, and the folder's copy wins). An old file
left empty is deleted, so once every repo has moved nothing waits. A known issue's key named its file by its absolute
path and now names it relative to the main checkout: a key is moved to the new form where a line of its file still
gives it, and the ledger's lines of the repo keep their order and their `v`, with those keys moved too.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import repodata
from .gitutil import git_root, main_worktree
from .state import DATA_ROOT, load_json, locked, save_json, short_hash, update_json

OLD_LEDGER = DATA_ROOT / "ledger.jsonl"
OLD_BASELINE = DATA_ROOT / "baseline.json"
OLD_COMMITS = DATA_ROOT / "commits.json"
OLD_PASSED = DATA_ROOT / "passed.json"
OLD_CHECKUP = DATA_ROOT / "checkup"  # a record per repo, by a hash of its main checkout
OLD_HOTSPOTS = DATA_ROOT / "hotspots"  # a scan's summary per worktree root, by a hash of it
OLD_DISMISSED = DATA_ROOT / "smells-dismissed.json"
OLD_SLOW = DATA_ROOT / "slow.json"
LEDGER_BYTES = 2_000_000  # the ledger's bound, as ledger.MAX_BYTES; over it the oldest lines go

Split = Callable[[dict], Tuple[dict, dict]]


def waiting() -> bool:
    """Whether any old shared file is still there to move records out of."""
    files = (OLD_LEDGER, OLD_BASELINE, OLD_COMMITS, OLD_PASSED, OLD_DISMISSED, OLD_SLOW)
    return any(p.exists() for p in files) or any(any(d.glob("*.json")) for d in (OLD_CHECKUP, OLD_HOTSPOTS))


def under(path: str, main: Path) -> bool:
    """Whether `path` is `main` or lies under it."""
    p = Path(path)
    return p == main or main in p.parents


def of_repo(root: str, main: Path) -> bool:
    """Whether a worktree root, as an old record keyed it, belongs to the repo of `main`."""
    if under(root, main):
        return True
    top = git_root(Path(root)) if Path(root).is_dir() else None
    return top is not None and main_worktree(top) == main


# ---------------------------------------------------------------- keys


def checkout(f: Path) -> Path:
    """`f` as the main checkout names it (gate.checkout_path, which the old keys hashed)."""
    root = git_root(f.parent) if f.parent.is_dir() else None
    if root is None:
        return f
    try:
        return main_worktree(root) / f.resolve().relative_to(root)
    except ValueError:
        return f


def rekeyed(key: str, e: dict) -> Optional[str]:
    """The new key of a finding whose old `key` hashed its file's absolute path; None when no line of the file gives
    the old key any more (its code changed, so the key matches nothing either way)."""
    f = checkout(Path(str(e.get("file") or "")))
    parts = f"{e.get('tool', '')}|{e.get('rule', '')}|{e.get('msg', '')}"
    try:
        texts = {row.strip() for row in f.read_text(errors="replace").splitlines()}
    except OSError:
        texts = set()
    for t in texts | {""}:
        if short_hash(f"{f}|{parts}|{t}") == key:
            return short_hash(f"{repodata.key_path(f)}|{parts}|{t}")
    return None


def key_map(main: Path) -> Dict[str, str]:
    """Old key to new for the repo's known issues and open findings."""
    entries = {k: e for k, e in load_json(OLD_BASELINE, {}).items()
               if isinstance(e, dict) and under(str(e.get("file") or ""), main)}
    for root, record in load_json(OLD_COMMITS, {}).items():
        if isinstance(record, dict) and of_repo(root, main):
            for part in ("pending", "earlier"):
                entries.update(record.get(part) or {})
    out = {k: rekeyed(k, e) for k, e in entries.items()}
    return {k: v for k, v in out.items() if v}


# ---------------------------------------------------------------- moving


def move_json(old: Path, new: Path, split: Split) -> None:
    """Move the part of the old JSON file that `split` gives as its first half into `new` (merged, what `new` holds
    already wins), then leave the old file with the rest, or delete it when nothing is left."""
    if not old.exists():
        return
    with locked(old):
        data = load_json(old, None)
        if not isinstance(data, dict):
            return
        mine, rest = split(data)
        if not mine:
            return
        update_json(new, {}, lambda cur: {**mine, **(cur if isinstance(cur, dict) else {})})
        if rest:
            save_json(old, rest)
        else:
            gone(old)


def gone(path: Path) -> None:
    """Delete the file at `path`; one already gone is fine."""
    try:
        path.unlink()
    except OSError:
        pass


def parted(data: dict, mine: Callable[[str, object], bool]) -> Tuple[dict, dict]:
    """`data` split into the items `mine` takes and the rest."""
    took = {k: v for k, v in data.items() if mine(k, v)}
    return took, {k: v for k, v in data.items() if k not in took}


def baseline_split(main: Path, keys: Dict[str, str]) -> Split:
    """The repo's known issues, under their new keys, each file relative to the main checkout."""
    def split(data: dict) -> Tuple[dict, dict]:
        took, rest = parted(data, lambda _k, e: isinstance(e, dict) and under(str(e.get("file") or ""), main))
        moved = {keys.get(k, k): {**e, "file": repodata.key_path(Path(str(e["file"])))} for k, e in took.items()}
        return moved, rest

    return split


def commits_split(main: Path, keys: Dict[str, str]) -> Split:
    """The repo's last-blocked records, their findings under their new keys."""
    def renamed(record: dict) -> dict:
        out = dict(record)
        for part in ("pending", "earlier"):
            if isinstance(record.get(part), dict):
                out[part] = {keys.get(k, k): e for k, e in record[part].items()}
        return out

    def split(data: dict) -> Tuple[dict, dict]:
        took, rest = parted(data, lambda root, v: isinstance(v, dict) and of_repo(root, main))
        return {root: renamed(v) for root, v in took.items()}, rest

    return split


def move_ledger(main: Path, new: Path, keys: Dict[str, str]) -> None:
    """Move the repo's lines of the old ledger ahead of what the new one holds, in their order, a key moved where
    `keys` says; then drop them from the old one."""
    if not OLD_LEDGER.exists():
        return
    with locked(OLD_LEDGER):
        try:
            rows = OLD_LEDGER.read_text().splitlines()
        except OSError:
            return
        mine: List[str] = []
        rest: List[str] = []
        needle = json.dumps(str(main))
        for raw in rows:
            row = parsed(raw) if needle in raw else None
            if row is None or row.get("repo") != str(main):
                rest.append(raw)
            elif row.get("key") in keys:
                mine.append(json.dumps({**row, "key": keys[row["key"]]}, separators=(",", ":")))
            else:
                mine.append(raw)
        if not mine:
            return
        with locked(new):
            try:
                after = new.read_text().splitlines()
            except OSError:
                after = []
            kept = newest(mine + after, LEDGER_BYTES * 3 // 4)
            write_lines(new, kept)
        if [r for r in rest if r.strip()]:
            write_lines(OLD_LEDGER, rest)
        else:
            gone(OLD_LEDGER)


def parsed(raw: str) -> Optional[dict]:
    """A ledger line as a dict; None for a torn one."""
    try:
        row = json.loads(raw)
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


def newest(rows: List[str], limit: int) -> List[str]:
    """All of `rows` when they fit in the ledger's bound, else the newest that fit in `limit` bytes."""
    if sum(len(r.encode()) + 1 for r in rows) <= LEDGER_BYTES:
        return rows
    size, out = 0, []
    for raw in reversed(rows):
        size += len(raw.encode()) + 1
        if size > limit:
            break
        out.append(raw)
    return out[::-1]


def write_lines(path: Path, rows: List[str]) -> None:
    """Write `rows` to `path` whole or not at all."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text("".join(r + "\n" for r in rows))
    tmp.replace(path)


def move_file(old: Path, new: Path) -> None:
    """Move the old record file to `new`, unless `new` is there already; then delete the old one."""
    if not old.exists():
        return
    with locked(old):
        data = load_json(old, None)
        if data is None:
            return
        if not new.exists():
            save_json(new, data)
        gone(old)
        gone(Path(f"{old}.lock"))
    if old.parent.is_dir() and not any(old.parent.iterdir()):
        try:
            old.parent.rmdir()
        except OSError:
            pass  # another repo's record came in meanwhile


def migrate(main: Path, folder: Path) -> None:
    """Move the records of the repo whose main checkout is `main` from the old shared files into `folder`."""
    if not waiting():
        return
    keys = key_map(main)
    move_json(OLD_BASELINE, folder / repodata.BASELINE, baseline_split(main, keys))
    move_json(OLD_COMMITS, folder / repodata.COMMITS, commits_split(main, keys))
    move_ledger(main, folder / repodata.LEDGER, keys)

    def mine(root: str, _v: object) -> bool:
        return of_repo(root, main)

    move_json(OLD_PASSED, folder / repodata.PASSED, lambda data: parted(data, mine))
    move_json(OLD_DISMISSED, folder / repodata.DISMISSED, lambda data: parted(data, mine))
    move_json(OLD_SLOW, folder / repodata.SLOW,
              lambda data: parted(data, lambda k, _v: under(k.partition(":")[2], main)))
    move_file(OLD_CHECKUP / f"{short_hash(str(main))}.json", folder / repodata.CHECKUP)
    move_file(OLD_HOTSPOTS / f"{short_hash(str(main))}.json", folder / repodata.HOTSPOTS / f"{short_hash(str(main))}.json")
