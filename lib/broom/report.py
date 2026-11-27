"""`broom report`: what the ledger says broom stopped, what was fixed and what went through, in the whole record or
from a broom version on.

A finding counts once: the ledger holds a block line each time a commit or a turn's end is blocked on it, and the
report counts the distinct findings, (repo, key), each by how it ended last: fixed, let through (with its `how`), or
still open (blocked, and neither fixed nor let through yet). A finding the user was asked about (an `ask` line) is no
outcome: it stays open until it is fixed or let through. The fix rate is fixed over fixed, let through and still open
after a question, so a question that nothing ended counts against its rule, and one still open otherwise doesn't
(decision 043). The self-waivers, changes that loosened the bar, are counted by kind beside that, with what each
`.broom.json` change was.
"""

from __future__ import annotations

import statistics
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from . import ledger
from .gate import display
from .gitutil import git_root, main_worktree

OUTCOMES = {"block": "open", "fix": "fixed", "pass": "let through"}
NUMBERS = {2, 3, 5, 6}  # the columns of the rule table that hold numbers
MOMENTS = {"commit": "at a commit", "pre-commit": "at a commit", "stop": "at a turn's end",
           "subagent-stop": "at a turn's end"}  # the hooks a whole check runs in, by the moment of Claude's flow
TEMP_ROOTS = tuple(dict.fromkeys(p for root in (tempfile.gettempdir(), "/tmp", "/var/folders")
                                 for p in (root.rstrip("/"), str(Path(root).resolve()))))


def scope(roots: List[Path]) -> Tuple[Set[str], Dict[str, List[str]]]:
    """The repos the roots are in, and per repo the paths inside it that narrow the report: none for a whole repo."""
    repos: Set[str] = set()
    narrow: Dict[str, List[str]] = defaultdict(list)
    for root in roots:
        top = git_root(root if root.is_dir() else root.parent)
        if top is None:
            raise SystemExit("broom: not inside a git repository")
        repo = str(main_worktree(top))
        rel = "." if root == top else str(root.relative_to(top))
        repos.add(repo)
        narrow[repo].append(rel)
    return repos, {r: rels for r, rels in narrow.items() if "." not in rels}


def wanted(row: dict, repos: Optional[Set[str]], narrow: Dict[str, List[str]]) -> bool:
    """Whether a ledger row is in the report's scope: its repo is in `repos` (any repo when None) and, where `narrow`
    limits that repo to paths, its file is under one of them. A row with no file is always kept."""
    if repos is not None and row.get("repo") not in repos:
        return False
    rels, file = narrow.get(str(row.get("repo"))), str(row.get("file") or "")
    return not (rels and file) or any(file == p or file.startswith(p + "/") for p in rels)


def throwaway(repo: str) -> bool:
    """Whether a repo lies in a temporary folder, where only a test or a trial puts one."""
    return any(repo == root or repo.startswith(root + "/") for root in TEMP_ROOTS)


def version_key(text: object) -> Optional[Tuple[int, ...]]:
    """A broom version such as `0.28.5` as numbers to compare (trailing zeros left out, so `1.0` is `1`), or None when
    it is no version."""
    parts = text.split(".") if isinstance(text, str) else []
    if not parts or not all(p.isascii() and p.isdigit() for p in parts):
        return None
    numbers = [int(n) for n in parts]
    while numbers and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers)


def window(since: Optional[str], repos: Optional[Set[str]], narrow: Dict[str, List[str]]) -> List[dict]:
    """The ledger rows that `wanted` keeps, oldest first: all of them, or with `since` (a version) only those written
    by that broom version or a later one. A row with no `v` is older than any version; one without a numeric time is
    skipped."""
    floor = version_key(since)
    every = ledger.every_row() if repos is None else (r for repo in sorted(repos) for r in ledger.rows_of(repo))
    rows = [r for r in every if isinstance(r.get("t"), (int, float))]
    if floor is not None:
        rows = [r for r in rows if (v := version_key(r.get("v"))) is not None and v >= floor]
    return sorted((r for r in rows if wanted(r, repos, narrow)), key=lambda r: r["t"])


def ended(rows: Iterable[dict]) -> Dict[Tuple[str, str], dict]:
    """Each finding of the rows, by (repo, key), with what it was, how it ended last and whether the user was `asked`
    about it."""
    out: Dict[Tuple[str, str], dict] = {}
    for r in rows:
        if r.get("event") == "ask" and (str(r.get("repo")), r.get("key")) in out:
            out[(str(r.get("repo")), r["key"])]["asked"] = True
        if r.get("event") not in OUTCOMES or not r.get("key"):
            continue
        f = out.setdefault((str(r.get("repo")), r["key"]), {"tool": r.get("tool", "?"), "rule": r.get("rule", "?")})
        f["outcome"] = OUTCOMES[r["event"]]
        f["how"] = r.get("how") if r["event"] == "pass" else None
    return out


def rate(fixed: int, through: int) -> Optional[float]:
    """Fixed over fixed plus let through, to three decimals; None when neither happened, which `percent` shows as a
    dash."""
    return round(fixed / (fixed + through), 3) if fixed + through else None


def tally(found: Iterable[dict]) -> dict:
    """Counts of the findings by how they ended: `blocked` (all of them), `fixed`, `let_through`, `open`,
    `open_asked` (the open ones the user was asked about), `how` (the let-through ones by `how`), `fix_rate` and
    `asked` (those the user was asked about, whatever became of them). An open finding the user was asked about counts
    against the fix rate: the code still holds it."""
    found = list(found)
    counts = Counter(f["outcome"] for f in found)
    how = Counter(f["how"] or "?" for f in found if f["outcome"] == "let through")
    fixed, through = counts["fixed"], counts["let through"]
    waiting = sum(1 for f in found if f["outcome"] == "open" and f.get("asked"))
    return {"blocked": sum(counts.values()), "fixed": fixed, "let_through": through, "open": counts["open"],
            "open_asked": waiting, "how": dict(how), "fix_rate": rate(fixed, through + waiting),
            "asked": sum(1 for f in found if f.get("asked"))}


def by_rule(found: Dict[Tuple[str, str], dict]) -> List[dict]:
    """The `tally` of each (rule, tool) pair among the findings, most blocked first and then by rule name. `found` is
    what `ended` returns."""
    groups: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for f in found.values():
        groups[(f["rule"], f["tool"])].append(f)
    out = [{"rule": rule, "tool": tool, **tally(fs)} for (rule, tool), fs in groups.items()]
    return sorted(out, key=lambda x: (-x["blocked"], x["rule"]))


def skips(rows: List[dict]) -> Dict[str, Dict[str, int]]:
    """How many `skip` rows each tool had, per kind of note (`timeout` or `missing`), with the tools sorted by name."""
    out: Dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r.get("event") == "skip":
            out[str(r.get("tool", "?"))][str(r.get("note", ":")).split(":", 1)[0]] += 1
    return {tool: dict(kinds) for tool, kinds in sorted(out.items())}


def spread(rows: List[dict], event: str, name: Callable[[dict], str]) -> Dict[str, dict]:
    """Per `name` of the `event` rows that hold seconds: the number of runs, the median and the longest seconds,
    sorted by name."""
    runs: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        if r.get("event") == event and isinstance(r.get("seconds"), (int, float)):
            runs[name(r)].append(float(r["seconds"]))
    return {c: {"runs": len(s), "median": round(statistics.median(s), 2), "max": max(s)}
            for c, s in sorted(runs.items())}


def seconds(rows: List[dict]) -> Dict[str, dict]:
    """Per tool, from the `time` rows: the number of runs, the median and the longest seconds."""
    return spread(rows, "time", lambda r: str(r.get("check", "?")))


def whole_checks(rows: List[dict]) -> Dict[str, dict]:
    """Per moment (at a commit, at a turn's end), from the `run` rows: how many whole checks ran a tool, with their
    median and longest seconds."""
    return spread(rows, "run", lambda r: MOMENTS.get(str(r.get("where")), str(r.get("where") or "?")))


def waivers(rows: List[dict]) -> dict:
    """The `waiver` rows: `count`, the count per `kind` (sorted by name) and the `config` ones' notes, oldest first."""
    found = [r for r in rows if r.get("event") == "waiver"]
    kinds = Counter(str(r.get("kind", "?")) for r in found)
    return {"count": len(found), "kinds": dict(sorted(kinds.items())),
            "config": [f"{r.get('file', '')} {r.get('note', '')}".strip() for r in found if r.get("kind") == "config"]}


def report(roots: List[Path], since: Optional[str] = None) -> dict:
    """The record of the repos `roots` are in: all of it, or the lines written by broom version `since` or later.
    Without roots it covers every repo but those in a temporary folder, which it counts in `left_out`."""
    repos, narrow = scope(roots) if roots else (None, {})
    rows = window(since, repos, narrow)
    left = {str(r.get("repo")) for r in rows if throwaway(str(r.get("repo")))} if repos is None else set()
    rows = [r for r in rows if str(r.get("repo")) not in left]
    found = ended(rows)
    return {"since": since, "repos": sorted(repos) if repos is not None else "all", "left_out": len(left), **tally(found.values()),
            "rules": by_rule(found), "skips": skips(rows), "seconds": seconds(rows), "checks": whole_checks(rows),
            "waivers": waivers(rows), "errors": sum(1 for r in rows if r.get("event") == "error")}


# ---------------------------------------------------------------- text


def percent(value: Optional[float]) -> str:
    """A fix rate as a whole percentage such as `75%`, or `-` when there is none."""
    return "-" if value is None else f"{round(value * 100)}%"


def through_text(t: dict) -> str:
    """The let-through cell of the rule table: the count with its breakdown by `how`, or `-` when nothing got
    through."""
    if not t["let_through"]:
        return "-"
    return f"{t['let_through']} (" + ", ".join(f"{how} {n}" for how, n in sorted(t["how"].items())) + ")"


def open_text(t: dict) -> str:
    """The count of open findings, with how many of them the user was asked about."""
    return f"{t['open']} (asked {t['open_asked']})" if t["open_asked"] else str(t["open"])


def rule_rows(rules: List[dict]) -> List[str]:
    """The rule table as lines of aligned text: a header, then one row per rule, with the number columns
    right-aligned."""
    head = ("rule", "tool", "blocked", "fixed", "let through", "open", "fix rate")
    table = [head] + [(x["rule"], x["tool"], str(x["blocked"]), str(x["fixed"]), through_text(x), open_text(x),
                       percent(x["fix_rate"])) for x in rules]
    widths = [max(len(row[c]) for row in table) for c in range(len(head))]
    return ["  ".join(cell.rjust(w) if c in NUMBERS else cell.ljust(w) for c, (cell, w) in enumerate(zip(row, widths)))
            .rstrip() for row in table]


def skip_rows(skips: Dict[str, Dict[str, int]]) -> List[str]:
    """One line per tool in the skip counts (from `skips`): its total, then the count per kind of note."""
    return [f"  {tool}: {sum(k.values())} (" + ", ".join(f"{kind} {n}" for kind, n in k.items()) + ")"
            for tool, k in skips.items()]


def second_rows(checks: Dict[str, dict]) -> List[str]:
    """One line per name in the seconds (from `spread`): median, longest and the number of runs."""
    return [f"  {c}: median {v['median']}, max {v['max']} ({v['runs']} run{'' if v['runs'] == 1 else 's'})"
            for c, v in checks.items()]


def waiver_rows(w: dict) -> List[str]:
    """The self-waivers (from `waivers`): the count per kind on one line, then each `config` note; none for none."""
    if not w["count"]:
        return []
    return ["  " + ", ".join(f"{kind} {n}" for kind, n in w["kinds"].items()), *[f"  {c}" for c in w["config"]]]


def render(data: dict) -> str:
    """The text `broom report` prints for `data` (from `report`): a summary, then each section that has something to
    show. With nothing recorded it is one line."""
    where = "every repo" if data["repos"] == "all" else ", ".join(display(Path(r)) for r in data["repos"])
    if data["left_out"]:
        where += f" but {data['left_out']} in a temporary folder"
    period = f"since {data['since']}" if data["since"] else "in the whole record"
    if not (data["blocked"] or data["skips"] or data["seconds"] or data["checks"] or data["errors"]
            or data["waivers"]["count"]):
        return f"broom: nothing recorded for {where} {period}"
    asked = f"asked the user {data['asked']}, " if data["asked"] else ""
    out = [f"broom report: {where}, {period}",
           f"blocked {data['blocked']}, fixed {data['fixed']}, let through {data['let_through']}, "
           f"still open {open_text(data)}, {asked}fix rate {percent(data['fix_rate'])}"]
    sections = [("By rule (each finding counts once; fix rate is fixed over fixed, let through and still open after a "
                 "question):",
                 [f"  {row}" for row in rule_rows(data["rules"])] if data["rules"] else []),
                ("Skipped checks, by tool:", skip_rows(data["skips"])),
                ("Seconds per whole check that ran a tool:", second_rows(data["checks"])),
                ("Seconds per tool:", second_rows(data["seconds"])),
                ("Self-waivers (changes that loosened the bar; shown, never blocked):", waiver_rows(data["waivers"]))]
    for title, rows in sections:
        out += ["", title, *rows] if rows else []
    if data["errors"]:
        out += ["", f"A hook failed and let the action through {data['errors']} time(s)."]
    return "\n".join(out)
