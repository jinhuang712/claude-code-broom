"""Known issues whose file names a linked worktree that is gone: broom before 0.28.1 kept the file of an issue accepted
in a linked worktree as the worktree named it, and keyed it on that path too. Once the worktree is deleted nothing maps
the path, so the entry hides nothing in the main checkout though the line may be there.

Such an entry is recovered when it can be proven: the tails of its path under the main checkout of the repo it sat in
are tried, and the one whose line texts give the entry's key again, under its old path or under the new one, is the
same finding. The entry then names that file and takes the key the main checkout gives it. One that can't be proven
stays as it is, and `broom known` still marks it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .gate import baseline_change, key_of, line_texts
from .gitutil import git_root, main_worktree


def main_of(f: Path) -> Optional[Path]:
    """The main checkout of the repo that holds `f`, found from the nearest folder above it still on disk."""
    here = next((p for p in f.parents if p.is_dir()), None)
    root = git_root(here) if here else None
    return main_worktree(root) if root else None


def tails(f: Path) -> List[Path]:
    """The files under the main checkout that `f`, a path in a worktree inside it that is gone, may be: each tail of
    its path below the main checkout, the longest first, that is a file, where what the tail leaves out is a folder
    no longer on disk. So a file deleted from the main checkout is no worktree's. Empty outside a repo."""
    main = main_of(f)
    if main is None:
        return []
    try:
        parts = f.resolve().relative_to(main).parts
    except ValueError:
        return []
    cuts = [i for i in range(1, len(parts)) if not main.joinpath(*parts[:i]).is_dir()]
    return [p for p in (main.joinpath(*parts[i:]) for i in cuts) if p.is_file()]


def proven(key: str, e: dict) -> Optional[Tuple[str, dict]]:
    """The key and the entry that the known issue `key` (entry `e`) takes once the file it names is found under the
    main checkout, where a line of that file gives `key` again; None when no tail proves it."""
    old = Path(str(e.get("file") or ""))
    parts = (str(e.get("tool", "")), str(e.get("rule", "")), str(e.get("msg", "")))
    for f in tails(old):
        texts = line_texts([f]) | (set() if e.get("line") else {""})
        for t in texts:
            if key in (key_of(old, *parts, t), key_of(f, *parts, t)):
                return key_of(f, *parts, t), {**e, "file": str(f)}
    return None


def recover(entries: Dict[str, dict]) -> Dict[str, dict]:
    """`entries` (known issues) with each one whose file is gone and that a tail proves (see `proven`) moved to the
    main checkout's file and key, in the baseline on disk too. The others are as they were."""
    found = {k: proven(k, e) for k, e in entries.items() if e.get("file") and not Path(str(e["file"])).exists()}
    moved = {k: v for k, v in found.items() if v is not None}
    if not moved:
        return entries

    def move(data: dict) -> None:
        for k, (new, e) in moved.items():
            data.pop(k, None)
            data[new] = e

    for main in {main_of(Path(str(e.get("file")))) for _, e in moved.values()}:
        baseline_change(main, move)
    out = {k: e for k, e in entries.items() if k not in moved}
    out.update(dict(moved.values()))
    return out
