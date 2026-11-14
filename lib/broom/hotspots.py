"""The repo's code smells as a whole, ranked worst first for whoever cleans up: Claude through /broom:clean, or a
person running `broom smells`. And the session note that tells Claude, once per session, when the repo has
smells past the hard limit, so it raises them with the user at a natural point. The user's "not now"
(`broom smells --dismiss`) keeps the note quiet until that count grows. The scan behind the note runs in the
background: on a 2,376-file repo it took 13 to 36 seconds, and Claude's first reply waits for session-start hooks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .common import DATA_ROOT, changed_since, drop_excluded, git, load_json, save_json, setting, short_hash
from .gate import display
from .smells import Smell, find_smells

CACHE = DATA_ROOT / "hotspots"
DISMISSED = DATA_ROOT / "smells-dismissed.json"
FILES_IN_NOTE = 3
NOTE_MAX_FILES = 5000  # past this, a session start doesn't scan: `broom smells` still does


def repo_files(repo: Path, paths: List[Path], base: Optional[str] = None) -> List[Path]:
    """The repo's files, or those changed since `base`, within `paths` (all when empty), minus .broom.json's
    `exclude`."""
    if base:
        files = changed_since(repo, base)
        if files is None:
            raise SystemExit(f"broom: unknown revision {base!r}")
    else:
        out = git(["ls-files", "--cached", "--others", "--exclude-standard"], repo) or ""
        files = [(repo / n).resolve() for n in out.splitlines() if n]
    files = [f for f in files if any(f == p or p in f.parents for p in paths)] if paths else files
    return drop_excluded(repo, files)


def severity(s: Smell) -> Tuple[bool, float]:
    """Past the hard limit first, then how far past its limit (a count, for smells without one)."""
    return s.level == "block", s.value / s.limit if s.limit else float(s.value)


def rank(smells: List[Smell]) -> Tuple[List[Smell], List[dict]]:
    """The smells worst first, and the files holding them, most smells past the hard limit first."""
    ordered = sorted(smells, key=severity, reverse=True)
    by_file: Dict[Path, List[Smell]] = {}
    for s in ordered:
        by_file.setdefault(s.file, []).append(s)
    files = [{"file": str(f.relative_to(rows[0].repo)), "severe": sum(s.level == "block" for s in rows),
              "hints": sum(s.level == "hint" for s in rows), "worst": rows[0].text()} for f, rows in by_file.items()]
    return ordered, sorted(files, key=lambda f: (f["severe"], f["hints"]), reverse=True)


def report(repo: Path, paths: List[Path], top: int, base: Optional[str] = None) -> dict:
    """The smells in `paths` (the repo when empty): counts, the `top` hotspot files and the `top` worst smells.
    With `base`, only what the changes since that revision made worse; each smell's `was` is then its size or
    count at `base`, None for a new one."""
    found, notes = find_smells(repo, repo_files(repo, paths, base), base)
    ordered, files = rank(found)
    severe = sum(s.level == "block" for s in found)
    smells = [{"file": str(s.file.relative_to(repo)), "line": s.line, "smell": s.metric, "level": s.level,
               "text": s.text(), "was": s.was if base else None} for s in ordered[:top]]
    return {"repo": str(repo), "base": base, "total": len(found), "severe": severe, "hints": len(found) - severe,
            "hotspots": files[:top], "smells": smells, "notes": notes}


def render(data: dict) -> str:
    where = f"the changes since {data['base']} made worse" if data["base"] else f"in {display(Path(data['repo']))}"
    rows = [f"[broom] {data['total']} code smell(s) {where}: {data['severe']} past the hard limit, "
            f"{data['hints']} hints."]
    if data["hotspots"]:
        rows += ["", "Hotspots:"] + [f"  {f['file']}  {f['severe']} severe, {f['hints']} hints; worst: {f['worst']}"
                                     for f in data["hotspots"]]
        rows += ["", "Worst smells:"] + [f"  {s['file']}:{s['line']}  {s['smell']}  {s['text']}"
                                         for s in data["smells"]]
    return "\n".join(rows + [f"note: {n}" for n in data["notes"]])


def head_of(repo: Path) -> str:
    return (git(["rev-parse", "HEAD"], repo) or "").strip()


def cached_summary(repo: Path) -> Optional[dict]:
    """The repo's smell counts at HEAD if a scan already counted them, else None: what a session start can read
    without waiting for a scan."""
    head = head_of(repo)
    cached = load_json(CACHE / f"{short_hash(str(repo))}.json", {})
    return cached if head and cached.get("head") == head else None


def summary(repo: Path) -> Optional[dict]:
    """The repo's smell counts at HEAD, scanned once per commit; None without a commit or past the size limit."""
    head = head_of(repo)
    if not head:
        return None
    cached = cached_summary(repo)
    if cached:
        return cached
    files = repo_files(repo, [])
    if len(files) > NOTE_MAX_FILES:
        return None
    found, _ = find_smells(repo, files, None)
    _, hot = rank(found)
    data = {"head": head, "total": len(found), "severe": sum(s.level == "block" for s in found),
            "hotspots": [f["file"] for f in hot[:FILES_IN_NOTE]]}
    save_json(CACHE / f"{short_hash(str(repo))}.json", data)
    return data


def session_note(repo: Path, data: Optional[dict]) -> Optional[str]:
    """The note that asks Claude to offer a cleanup, from a summary: none when smells are off, there are no severe
    ones, or the user dismissed this many."""
    if setting("smells", repo) == "off":
        return None
    if not data or not data["severe"] or data["severe"] <= load_json(DISMISSED, {}).get(str(repo), -1):
        return None
    return (f"broom found {data['severe']} code smell(s) past the hard limit in this repo ({data['total']} in all; "
            f"worst files: {', '.join(data['hotspots'])}). Don't interrupt the user's task for this: at a natural "
            "point, tell them and offer /broom:clean, which ranks the smells and cleans up worst first. Don't clean "
            "up without their go-ahead. If they say not now, run `broom smells --dismiss`: broom then stays quiet "
            "until the count grows.")


def dismiss(repo: Path) -> str:
    data = summary(repo) or {"severe": 0}
    seen = load_json(DISMISSED, {})
    seen[str(repo)] = data["severe"]
    save_json(DISMISSED, seen)
    return f"broom: the session note stays quiet until this repo has more than {data['severe']} severe smell(s)"
