"""The repo's code smells as a whole, ranked worst first for whoever cleans up: Claude by its clean skill, or a
person running `broom smells`. And the session note that tells Claude, once per session, when the repo has
smells past the hard limit, so it raises them with the user at a natural point. The user's "not now"
(`broom smells --dismiss`) cuts the note to one line with the count until that count grows. The scan behind the
note runs in the background: on a 2,376-file repo it took 13 to 36 seconds, and Claude's first reply waits for
session-start hooks.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from .config import DEAD_CODE, SMELL_PRESENCE, drop_excluded, repo_config, setting
from .findings import Issue
from .gate import baseline_keys, display, issue_key, note_text
from .gitutil import changed_since, git
from .sizes import SIZED, find_sizes
from .smell import DESCRIBE, LABELS
from .smells import Smell, find_smells
from .state import DATA_ROOT, load_json, save_json, short_hash, update_json
from .statsgit import commits_per_file
from .testrot import DUPLICATE_TESTS, duplicate_counter

CACHE = DATA_ROOT / "hotspots"
DISMISSED = DATA_ROOT / "smells-dismissed.json"
FILES_IN_NOTE = 3
NOTE_MAX_FILES = 5000  # past this, a session start doesn't scan: `broom smells` still does
SCAN_SECONDS = 20  # what the tools that run in the real tree have between them in that scan
CHURN_DAYS = 90  # how far back a file's changes are counted
SEVERE_WEIGHT = 3  # a smell past the hard limit weighs this much against a hint in a file's score
ORDERS = {"churn": lambda f: (f["score"], f["severe"], f["hints"]), "smells": lambda f: (f["severe"], f["hints"])}
# The tools whose findings make up each of the check-up's smell counters: a note that names one of them means the
# count is short of what the code holds.
COUNTED_BY = {DEAD_CODE: ("jscpd",), "missing_docs": ("ruff", "golangci-lint", "swiftlint", "oxlint", "node is missing"),
              "deprecated_api": ("ruff", "golangci-lint", "clippy", "oxlint", "tsgolint")}
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


def order_text(by: str, days: int = CHURN_DAYS) -> str:
    """How hotspots are ordered, in words: `by` is "churn" or "smells"."""
    if by == "churn":
        return f"by score = ({SEVERE_WEIGHT} x severe + hints) x (1 + changes in the last {days} days)"
    return "most severe first"


def churn_order(repo: Path, by: str = "churn", days: int = CHURN_DAYS,
                at: Optional[int] = None) -> Tuple[Dict[str, int], str, List[str]]:
    """The commits per file of the last `days` days (before the Unix time `at`, when given), the order the hotspots
    can have and a note when it isn't the one asked for: `by` is "churn" or "smells", and ranking by churn needs
    history."""
    churn = dict(commits_per_file(repo, days, at) or {})
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
        severe, hints = sum(s.level == "block" for s in rows), sum(s.level != "block" for s in rows)
        changes = churn.get(rel, 0)
        files.append({"file": rel, "severe": severe, "hints": hints, "changes": changes,
                      "score": score(severe, hints, changes), "worst": rows[0].text()})
    return ordered, sorted(files, key=ORDERS[by], reverse=True)


def smell_row(repo: Path, s: Smell, base: Optional[str] = None) -> dict:
    """One smell as the JSON and the worst-smells list show it; `was` is its size or count at `base`, None for a
    new smell and without a base."""
    return {"file": str(s.file.relative_to(repo)), "line": s.line, "smell": s.metric, "level": s.level,
            "text": s.text(), "was": s.was if base else None}


def lines_of(s: Smell) -> List[int]:
    """The lines the smell `s` stands on: each occurrence of an occurrence smell, else its first line."""
    return list(s.added) if s.metric in SMELL_PRESENCE else [s.line]


def standing_issue(s: Smell, line: int) -> Issue:
    """The smell `s` at `line` as the known-issue store keys it: an occurrence by its kind alone, so the key follows
    the text of its line; a sized smell by its message as a whole-repo scan words it, so the key follows its size."""
    msg = LABELS[s.metric] if s.metric in SMELL_PRESENCE else replace(s, compared=False, touched=False).text()
    return Issue("smells", s.repo, s.file, line, 0, s.metric, msg)


def drop_known(found: List[Smell], known: Optional[Set[str]] = None) -> Tuple[List[Smell], List[Smell]]:
    """`found` split by the known-issue store (`known`, read from disk when None): the open smells, and the known ones,
    collapsed but still counted. An occurrence smell loses its known lines, and goes when none is left; each known
    line is a known smell of its own, as each was accepted on its own."""
    known = baseline_keys() if known is None else known
    if not known:
        return list(found), []
    kept: List[Smell] = []
    hidden: List[Smell] = []
    for s in found:
        lines = lines_of(s)
        left = [n for n in lines if issue_key(standing_issue(s, n)) not in known]
        gone = [n for n in lines if n not in left]
        hidden += [replace(s, line=n, added=[n], value=1) if s.metric in SMELL_PRESENCE else s for n in gone]
        if left and gone:
            s = replace(s, line=left[0], added=left, value=s.value - len(gone))
        if left:
            kept.append(s)
    return kept, hidden


def counts(kept: List[Smell], hidden: List[Smell]) -> Dict[str, int]:
    """The counts every report gives: `total`, `severe` and `hints` count the known smells too, `known` says how many
    of them are known (collapsed, not listed) and `open` how many are not."""
    severe = sum(s.level == "block" for s in kept + hidden)
    total = len(kept) + len(hidden)
    return {"total": total, "severe": severe, "hints": total - severe, "known": len(hidden), "open": len(kept)}


class Ask(NamedTuple):
    """What `broom smells` was asked for: how many rows, the revision to compare with, the order of the hotspots
    ("churn" or "smells"), and the kinds of smell to keep (all when empty)."""

    top: int = 10
    base: Optional[str] = None
    by: str = "churn"
    only: Tuple[str, ...] = ()


def report(repo: Path, paths: List[Path], ask: Ask) -> dict:
    """The smells in `paths` (the repo when empty): counts, the `top` hotspot files and the `top` worst smells.
    With `base`, only what the changes since that revision made worse; each smell's `was` is then its size or
    count at `base`, None for a new one. With `only`, the smells of those kinds alone, so the worst of one kind
    come first: the longest functions, say. The `by` returned is the order the hotspots really have. With `only`
    naming one of `SIZED` and no `base`, `sizes` goes on where the smells end: see `size_rows`."""
    churn, order, history_notes = churn_order(repo, ask.by)
    files = repo_files(repo, paths, ask.base)
    found, notes = find_smells(repo, files, ask.base)
    kept, hidden = drop_known([s for s in found if not ask.only or s.metric in ask.only])
    ordered, hotspots = rank(kept, churn, order)
    data = {"repo": str(repo), "base": ask.base, "only": list(ask.only), **counts(kept, hidden), "by": order,
            "hotspots": hotspots[:ask.top],
            "smells": [smell_row(repo, s, ask.base) for s in ordered[:ask.top]], "notes": notes + history_notes}
    if len(ask.only) == 1 and ask.only[0] in SIZED and not ask.base:
        data["sizes"], more = size_rows(repo, files, ask.only[0], ask.top - len(data["smells"]))
        data["notes"] = list(dict.fromkeys(data["notes"] + more))
    return data


def size_rows(repo: Path, files: List[Path], metric: str, room: int) -> Tuple[List[dict], List[str]]:
    """The next `room` longest of `metric` under the soft limit, as the JSON shows them, and the notes of the
    measuring: the sizes that fill a `--top` list the smells leave short. They are no smells and change no count."""
    rows, notes = find_sizes(repo, files, metric, room)
    return [{"file": r.rel, "line": r.line, "name": r.key, "value": r.value} for r in rows], notes


def hotspot_line(f: dict) -> str:
    """One hotspot row of the text report."""
    return (f"  {f['file']}  {f['severe']} severe, {f['hints']} hints, {f['changes']} changes, score {f['score']}; "
            f"worst: {f['worst']}")


def worst_rows(data: dict) -> List[str]:
    """The hotspots and the worst smells of the text report; nothing when there are no smells."""
    if not data["hotspots"]:
        return []
    rows = ["", f"Hotspots, {order_text(data['by'])}:"] + [hotspot_line(f) for f in data["hotspots"]]
    rows += ["", "Worst smells:"] + [f"  {s['file']}:{s['line']}  {s['smell']}  {s['text']}" for s in data["smells"]]
    listed = data.get("open", data["total"])
    if listed > len(data["smells"]):
        rows.append(f"  ... and {listed - len(data['smells'])} more; `--top {listed}` lists them all")
    return rows


def size_lines(data: dict) -> List[str]:
    """The sizes under the limit of the text report, one row like a smell's: file and line, kind, what it is."""
    metric = data["only"][0] if data.get("sizes") else ""
    rows = [f"  {s['file']}:{s['line']}  {metric}  {DESCRIBE[metric].format(key=s['name'], value=s['value'])}"
            for s in data.get("sizes") or []]
    return ["", "Longest under the limit (not smells):"] + rows if rows else []


def render(data: dict) -> str:
    """The report for a person. Missing tools go in the first line: counts without them read as cleaner than the
    code is."""
    where = f"the changes since {data['base']} made worse" if data["base"] else f"in {display(Path(data['repo']))}"
    missing = [note_text(n) for n in data["notes"] if n.startswith("missing:")]
    kinds = f" of {', '.join(data['only'])}" if data.get("only") else ""
    first = (f"[broom] {data['total']} code smell(s){kinds} {where}: {data['severe']} past the hard limit, "
             f"{data['hints']} hints{known_part(data.get('known') or 0)}."
             + (f" Not all measured, missing: {'; '.join(missing)}." if missing else ""))
    rows = [first] + worst_rows(data) + size_lines(data)
    return "\n".join(rows + [f"note: {note_text(n)}" for n in data["notes"] if not n.startswith("missing:")])


def known_part(known: int) -> str:
    """How many of a count are accepted as known, as the count's line ends: they count, but no list shows them."""
    return f"; {known} accepted as known, collapsed" if known else ""


def smell_counts(repo: Path, found: List[Smell], notes: List[str]) -> Dict[str, Optional[Dict[str, int]]]:
    """The check-up's smell counters from a scan of the whole repo (`found` has no base): per file, how many dead-code
    findings, public declarations with no doc comment, calls to deprecated APIs and duplicate test blocks it holds. A
    counter is None when the repo turned its smell off or a tool behind it was missing, failed or cut short: a count
    that low would read as a fall."""
    off = repo_config(repo).get("smells_off") or []
    out: Dict[str, Optional[Dict[str, int]]] = {}
    for metric, tools in COUNTED_BY.items():
        per_file: Dict[str, int] = {}
        for s in found:
            if s.metric == metric:
                rel = str(s.file.relative_to(repo))
                per_file[rel] = per_file.get(rel, 0) + s.value
        short = any(tool in note for note in notes for tool in tools)
        out[metric] = None if metric in off or short else per_file
    out[DUPLICATE_TESTS] = duplicate_counter(repo, found, notes, off)
    return out


def head_of(repo: Path) -> str:
    """The HEAD commit of the repo as a hash, or an empty string when it has none."""
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
    kept, hidden = drop_known(found)
    _, hot = rank(kept, churn, order)
    tally = counts(kept, hidden)
    data = {"head": head, "total": tally["total"], "severe": tally["severe"], "known": tally["known"],
            "open_severe": sum(s.level == "block" for s in kept), "hotspots": [f["file"] for f in hot[:FILES_IN_NOTE]],
            "partial": any(n.startswith("timeout:") for n in notes),  # the time ran out: the counts are a floor
            "counts": smell_counts(repo, found, notes)}
    save_json(CACHE / f"{short_hash(str(repo))}.json", data)
    return data


def session_note(repo: Path, data: Optional[dict]) -> Optional[str]:
    """The note on the repo's smells, from a summary: none when smells are off or none is past the hard limit. It asks
    Claude to offer a cleanup while an open one is past the hard limit and the user hasn't dismissed this many; else it
    only gives the count, in one line, so what was dismissed or accepted is never out of sight."""
    if setting("smells", repo) == "off" or not data or not data["severe"]:
        return None
    floor = "at least " if data.get("partial") else ""  # a scan that ran out of time counted only what it reached
    known = known_part(data.get("known") or 0)
    dismissed = data["severe"] <= load_json(DISMISSED, {}).get(str(repo), -1)
    if dismissed or not data.get("open_severe", data["severe"]):
        return (f"broom: {floor}{data['severe']} code smell(s) past the hard limit in this repo "
                f"({data['total']} in all{known}). Don't raise a cleanup for them.")
    return (f"broom found {floor}{data['severe']} code smell(s) past the hard limit in this repo ({data['total']} in all"
            f"{known}; worst files: {', '.join(data['hotspots'])}). Don't interrupt the user's task for this: at a "
            "natural point, tell them and offer to clean up worst first. Don't clean up without their go-ahead: once "
            "they agree, load broom's clean skill, which is no command for them to type. If they say not now, run "
            "`broom smells --dismiss`: broom then only gives the count until it grows.")


def dismiss(repo: Path) -> str:
    """Stop the session note asking for a cleanup in this repo until it has more severe smells than now; it still
    gives the count. Returns the message to show."""
    data = summary(repo) or {"severe": 0}
    update_json(DISMISSED, {}, lambda seen: seen.update({str(repo): data["severe"]}))
    return (f"broom: the session note only gives the count, and asks for no cleanup, until this repo has more than "
            f"{data['severe']} severe smell(s)")
