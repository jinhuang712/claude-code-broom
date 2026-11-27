"""Where what broom finds in a repo is kept: `.broom/` in the repo's main checkout, so every linked worktree reads and
writes the same folder, the records move with the repo, and they go when it is deleted.

The folder holds a `.gitignore` of `*`, written when it is made, so git ignores it without a change to the repo's own
ignore files. A `.broom/` that git tracks came with the repo and is never read: the repo's records then live in a
folder of its own under the data directory, as they do when the repo's root can't be written, and a note says so.
Whether a repo's folder is its own is asked of git once, when broom first keeps something there, and the data
directory's index remembers it: an idle hook starts no git for it.

What has no repo (a line about a folder outside any) is kept in the data directory's `outside` folder. The tools'
caches, sessions, setup answers and the doctor's cache stay in the data directory too: they are the machine's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .gitutil import git, git_root, main_worktree
from .state import DATA_ROOT, load_json, short_hash, update_json

NAME = ".broom"
IGNORE = "*\n"  # the folder's own .gitignore: git ignores all of it, the .gitignore too
INDEX = DATA_ROOT / "repos.json"  # the main checkouts that keep a folder, own or spare: what `broom report --all` reads
SPARES = DATA_ROOT / "repos"  # a folder per repo whose own can't be used, by a hash of its main checkout
OUTSIDE = DATA_ROOT / "outside"  # for what lies in no repo
# The records each folder holds, by file name.
BASELINE = "baseline.json"  # known issues, each file relative to the main checkout
COMMITS = "commits.json"  # per worktree root: what its last commit or turn end blocked
LEDGER = "ledger.jsonl"
PASSED = "passed.json"  # per worktree root: content that passed
CHECKUP = "checkup.json"
HOTSPOTS = "hotspots"  # a folder: the session scan's cache, per worktree root
DISMISSED = "dismissed.json"  # per worktree root: the severe smells the user said not now to
SLOW = "slow.json"  # the checks that ran out of time, by the HEAD they ran out at
WHY = "why.txt"  # in a spare folder: why the repo's own isn't used
TRACKED = "tracked"
UNWRITABLE = "unwritable"

_known: Dict[Tuple[str, str], Path] = {}  # (index, main checkout) -> its folder, once settled in this process


def main_of(place: Path) -> Optional[Path]:
    """The main checkout of the repo that holds `place` (a file or a folder, found from the nearest folder above it
    still on disk); None outside any repo. No git starts for it."""
    here = place if place.is_dir() else next((p for p in place.parents if p.is_dir()), None)
    root = git_root(here) if here else None
    return main_worktree(root) if root else None


def key_path(file: Path) -> str:
    """`file` as a known issue's key names it: relative to its repo's main checkout, so moving the repo keeps the key;
    the path itself outside any repo."""
    main = main_of(file)
    for candidate in (file, file.resolve()) if main else ():
        try:
            return candidate.relative_to(main).as_posix()
        except ValueError:
            continue
    return str(file)


def tree_key(root: Path, main: Path) -> str:
    """How the folder of `main` names one of its worktrees, so a moved repo keeps the name: "." for the main checkout,
    its path relative to it for a worktree inside it, its absolute path only for a linked worktree outside it."""
    if root == main:
        return "."
    try:
        return root.relative_to(main).as_posix()
    except ValueError:
        return str(root)


def tree_root(key: str, main: Path) -> Path:
    """The worktree root that `tree_key` named `key` in the folder of `main`."""
    if key == ".":
        return main
    return Path(key) if Path(key).is_absolute() else main / key


def tree_name(root: Path) -> str:
    """`tree_key` of the worktree root `root` in its own repo's folder; the path itself outside any repo."""
    main = main_of(root)
    return tree_key(root, main) if main else str(root)


def spare(main: Path) -> Path:
    """The folder under the data directory that stands in for the repo's own."""
    return SPARES / short_hash(str(main))


def indexed() -> List[str]:
    """The main checkouts the index lists."""
    raw = load_json(INDEX, [])
    return [p for p in raw if isinstance(p, str)] if isinstance(raw, list) else []


def folder(main: Path) -> Path:
    """The folder that keeps the records of the repo whose main checkout is `main`, for reading. A repo broom kept
    nothing for yet, with no old records waiting to move, gets its own folder's path, which may not be there: a read
    finds nothing and no git starts. Otherwise the folder is settled (see `settle`)."""
    key = (str(INDEX), str(main))
    if key in _known:
        return _known[key]
    own, other = main / NAME, spare(main)
    if other.is_dir():
        found = other
    elif own.is_dir() and str(main) in indexed():
        found = own
    else:
        from .migrate import waiting

        if not own.is_dir() and not waiting():
            return own
        found = settle(main)
    _known[key] = found
    return found


def made(main: Path) -> Path:
    """The repo's folder, made if it isn't there yet: for writing."""
    found = folder(main)
    if found.is_dir() or not main.is_dir():
        return found
    found = settle(main)
    _known[(str(INDEX), str(main))] = found
    return found


def settle(main: Path) -> Path:
    """Decide where the repo keeps its records, make the folder, list it in the index and move the repo's old records
    into it. Its own `.broom/` unless git tracks a file in it or it can't be written; then a spare folder, with why."""
    own = main / NAME
    if not main.is_dir():
        return own  # a repo that is gone keeps nothing
    tracked = bool((git(["ls-files", "--", NAME], main) or "").strip())
    found, why = (spare(main), TRACKED) if tracked else (own, "")
    if not tracked:
        try:
            own.mkdir(exist_ok=True)
            if not (own / ".gitignore").exists():
                (own / ".gitignore").write_text(IGNORE)
        except OSError:
            found, why = spare(main), UNWRITABLE
    if why:
        found.mkdir(parents=True, exist_ok=True)
        (found / WHY).write_text(why)
    update_json(INDEX, [], lambda paths: sorted({*(p for p in paths if isinstance(p, str)), str(main)}))
    from .migrate import migrate

    migrate(main, found)
    return found


def at(place: Path) -> Path:
    """The folder that keeps the records of the repo that holds `place`, for reading; `OUTSIDE` for no repo."""
    main = main_of(place)
    return folder(main) if main else OUTSIDE


def made_at(place: Path) -> Path:
    """The folder that keeps the records of the repo that holds `place`, made if missing: for writing."""
    main = main_of(place)
    if main is None:
        OUTSIDE.mkdir(parents=True, exist_ok=True)
        return OUTSIDE
    return made(main)


def note(place: Path) -> Optional[str]:
    """What to tell when the repo of `place` keeps its records in a spare folder, and why; None when it uses its own."""
    main = main_of(place)
    if main is None or not spare(main).is_dir():
        return None
    try:
        why = (spare(main) / WHY).read_text().strip()
    except OSError:
        why = ""
    reason = ("git tracks files in this repo's .broom/, so they came with the repo and broom never reads them"
              if why == TRACKED else "this repo's root can't be written")
    return f"broom: {reason}; it keeps this repo's records in its own data directory instead."


def tracked(main: Path) -> bool:
    """Whether git tracks a file in the repo's own `.broom/`: then it came with the repo and is never read. One git
    call: for a command, never for a hook."""
    return (main / NAME).is_dir() and bool((git(["ls-files", "--", NAME], main) or "").strip())


def every() -> List[Path]:
    """The main checkouts of the index whose folder is still there; a repo deleted or moved since leaves the index."""
    listed = indexed()
    kept = [p for p in listed if (Path(p) / NAME).is_dir() or spare(Path(p)).is_dir()]
    if len(kept) != len(listed):
        update_json(INDEX, [], lambda paths: [p for p in paths if p in kept])
    return [Path(p) for p in kept]
