"""The repo's code smells as a whole, ranked worst first for whoever cleans up: Claude through /broom:clean, or a
person running `broom smells`. And the session note that tells Claude, once per session, when the repo has
smells past the hard limit, so it raises them with the user at a natural point. The user's "not now"
(`broom smells --dismiss`) keeps the note quiet until that count grows. The scan behind the note runs in the
background: on a 2,376-file repo it took 13 to 36 seconds, and Claude's first reply waits for session-start hooks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import drop_excluded, setting
from .gate import display, note_text
from .gitutil import changed_since, git
from .smells import Smell, find_smells
from .state import DATA_ROOT, load_json, save_json, short_hash, update_json
from .statsgit import commits_per_file

CACHE = DATA_ROOT / "hotspots"
DISMISSED = DATA_ROOT / "smells-dismissed.json"
FILES_IN_NOTE = 3
NOTE_MAX_FILES = 5000  # past this, a session start doesn't scan: `broom smells` still does
SCAN_SECONDS = 20  # what the tools that run in the real tree have between them in that scan
CHURN_DAYS = 90  # how far back a file's changes are counted
SEVERE_WEIGHT = 3  # a smell past the hard limit weighs this much against a hint in a file's score
HOTSPOTS_TITLE = {
    "churn": f"Hotspots, by score = ({SEVERE_WEIGHT} x severe + hints) x (1 + changes in the last {CHURN_DAYS} days):",
    "smells": "Hotspots, most severe first:",
}
ORDERS = {"churn": lambda f: (f["score"], f["severe"], f["hints"]), "smells": lambda f: (f["severe"], f["hints"])}
NO_HISTORY = "no commits in the last {days} days, or git log failed: the hotspots are ordered by their smells"


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


def score(severe: int, hints: int, changes: int) -> int:
    """A file's cost: its smells (one past the hard limit weighs `SEVERE_WEIGHT` hints) times one more than the
    commits that touched it, so a bad file that changes every week comes before one nobody touches."""
    return (SEVERE_WEIGHT * severe + hints) * (1 + changes)


def churn_order(repo: Path, by: str = "churn", days: int = CHURN_DAYS) -> Tuple[Dict[str, int], str, List[str]]:
    """The commits per file of the last `days` days, the order the hotspots can have and a note when it isn't the
    one asked for: `by` is "churn" or "smells", and ranking by churn needs history."""
    churn = dict(commits_per_file(repo, days) or {})
    if by == "churn" and not churn:
        return churn, "smells", [NO_HISTORY.format(days=days)]
    return churn, by, []


def rank(smells: List[Smell], churn: Dict[str, int], by: str = "churn") -> Tuple[List[Smell], List[dict]]:
    """The smells worst first, and the files holding them: by score, which counts `churn` (commits per file), or with
    `by` "smells" by their smells alone, the most past the hard limit first."""
    ordered = sorted(smells, key=severity, reverse=True)
    by_file: Dict[Path, List[Smell]] = {}
    for s in ordered:
        by_file.setdefault(s.file, []).append(s)
    files = []
    for f, rows in by_file.items():
        rel = str(f.relative_to(rows[0].repo))
        severe, hints = sum(s.level == "block" for s in rows), sum(s.level == "hint" for s in rows)
        changes = churn.get(rel, 0)
        files.append({"file": rel, "severe": severe, "hints": hints, "changes": changes,
                      "score": score(severe, hints, changes), "worst": rows[0].text()})
    return ordered, sorted(files, key=ORDERS[by], reverse=True)


def smell_row(repo: Path, s: Smell, base: Optional[str] = None) -> dict:
    """One smell as the JSON and the worst-smells list show it; `was` is its size or count at `base`, None for a
    new smell and without a base."""
    return {"file": str(s.file.relative_to(repo)), "line": s.line, "smell": s.metric, "level": s.level,
            "text": s.text(), "was": s.was if base else None}


def report(repo: Path, paths: List[Path], top: int, base: Optional[str] = None, by: str = "churn") -> dict:
    """The smells in `paths` (the repo when empty): counts, the `top` hotspot files and the `top` worst smells.
    With `base`, only what the changes since that revision made worse; each smell's `was` is then its size or
    count at `base`, None for a new one. `by` orders the hotspots, "churn" or "smells"; the `by` returned is the
    order they really have."""
    churn, order, history_notes = churn_order(repo, by)
    found, notes = find_smells(repo, repo_files(repo, paths, base), base)
    ordered, files = rank(found, churn, order)
    severe = sum(s.level == "block" for s in found)
    return {"repo": str(repo), "base": base, "total": len(found), "severe": severe, "hints": len(found) - severe,
            "by": order, "hotspots": files[:top], "smells": [smell_row(repo, s, base) for s in ordered[:top]],
            "notes": notes + history_notes}


def hotspot_line(f: dict) -> str:
    """One hotspot row of the text report."""
    return (f"  {f['file']}  {f['severe']} severe, {f['hints']} hints, {f['changes']} changes, score {f['score']}; "
            f"worst: {f['worst']}")


def render(data: dict) -> str:
    """The report for a person. Missing tools go in the first line: counts without them read as cleaner than the
    code is."""
    where = f"the changes since {data['base']} made worse" if data["base"] else f"in {display(Path(data['repo']))}"
    missing = [note_text(n) for n in data["notes"] if n.startswith("missing:")]
    rows = [f"[broom] {data['total']} code smell(s) {where}: {data['severe']} past the hard limit, "
            f"{data['hints']} hints." + (f" Not all measured, missing: {'; '.join(missing)}." if missing else "")]
    if data["hotspots"]:
        rows += ["", HOTSPOTS_TITLE[data["by"]]] + [hotspot_line(f) for f in data["hotspots"]]
        rows += ["", "Worst smells:"] + [f"  {s['file']}:{s['line']}  {s['smell']}  {s['text']}"
                                         for s in data["smells"]]
        if data["total"] > len(data["smells"]):
            rows.append(f"  ... and {data['total'] - len(data['smells'])} more; `--top {data['total']}` lists them all")
    return "\n".join(rows + [f"note: {note_text(n)}" for n in data["notes"] if not n.startswith("missing:")])


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
    if cached and not cached.get("partial"):
        return cached
    files = repo_files(repo, [])
    if len(files) > NOTE_MAX_FILES:
        return None
    churn, order, _ = churn_order(repo)  # first: a scan that uses the hook's time up leaves none for git
    found, notes = find_smells(repo, files, None, budget=SCAN_SECONDS)
    _, hot = rank(found, churn, order)
    data = {"head": head, "total": len(found), "severe": sum(s.level == "block" for s in found),
            "hotspots": [f["file"] for f in hot[:FILES_IN_NOTE]],
            "partial": any(n.startswith("timeout:") for n in notes)}  # the time ran out: the counts are a floor
    save_json(CACHE / f"{short_hash(str(repo))}.json", data)
    return data


def session_note(repo: Path, data: Optional[dict]) -> Optional[str]:
    """The note that asks Claude to offer a cleanup, from a summary: none when smells are off, there are no severe
    ones, or the user dismissed this many."""
    if setting("smells", repo) == "off":
        return None
    if not data or not data["severe"] or data["severe"] <= load_json(DISMISSED, {}).get(str(repo), -1):
        return None
    floor = "at least " if data.get("partial") else ""  # a scan that ran out of time counted only what it reached
    return (f"broom found {floor}{data['severe']} code smell(s) past the hard limit in this repo ({data['total']} in all; "
            f"worst files: {', '.join(data['hotspots'])}). Don't interrupt the user's task for this: at a natural "
            "point, tell them and offer /broom:clean, which ranks the smells and cleans up worst first. Don't clean "
            "up without their go-ahead. If they say not now, run `broom smells --dismiss`: broom then stays quiet "
            "until the count grows.")


def dismiss(repo: Path) -> str:
    data = summary(repo) or {"severe": 0}
    update_json(DISMISSED, {}, lambda seen: seen.update({str(repo): data["severe"]}))
    return f"broom: the session note stays quiet until this repo has more than {data['severe']} severe smell(s)"
