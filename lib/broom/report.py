"""`broom report`: what the ledger says broom stopped, what was fixed and what went through, over a period.

A finding counts once: the ledger holds a block line each time a commit or a turn's end is blocked on it, and the
report counts the distinct findings, (repo, key), each by how it ended last: fixed, let through (with its `how`), or
still open (blocked, and neither fixed nor let through yet). The fix rate is fixed over fixed plus let through, so a
finding that hasn't ended doesn't count against a rule. The self-waivers, changes that loosened the bar, are counted by
kind beside that, with what each `.broom.json` change was. A finding the user was asked about (an `ask` line) is no
outcome: it stays open until it is fixed or let through, and the report says how many were asked.
"""

from __future__ import annotations

import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from . import ledger
from .gate import display
from .gitutil import git_root, main_worktree

OUTCOMES = {"block": "open", "fix": "fixed", "pass": "let through"}
NUMBERS = {2, 3, 5, 6}  # the columns of the rule table that hold numbers


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


def window(days: int, repos: Optional[Set[str]], narrow: Dict[str, List[str]]) -> List[dict]:
    """The ledger rows of the last `days` days that `wanted` keeps, oldest first; a row without a numeric time is
    skipped."""
    cutoff = time.time() - days * 86400
    rows = [r for r in ledger.read(ledger.LEDGER) if isinstance(r.get("t"), (int, float)) and r["t"] >= cutoff]
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
    """Counts of the findings by how they ended: `blocked` (all of them), `fixed`, `let_through`, `open`, `how` (the
    let-through ones by `how`), `fix_rate` and `asked` (those the user was asked about, whatever became of them)."""
    counts = Counter(f["outcome"] for f in found)
    how = Counter(f["how"] or "?" for f in found if f["outcome"] == "let through")
    fixed, through = counts["fixed"], counts["let through"]
    return {"blocked": sum(counts.values()), "fixed": fixed, "let_through": through, "open": counts["open"],
            "how": dict(how), "fix_rate": rate(fixed, through), "asked": sum(1 for f in found if f.get("asked"))}


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


def seconds(rows: List[dict]) -> Dict[str, dict]:
    """Per check, from the `time` rows: the number of runs, the median and the longest seconds; the checks sorted by
    name."""
    runs: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        if r.get("event") == "time" and isinstance(r.get("seconds"), (int, float)):
            runs[str(r.get("check", "?"))].append(float(r["seconds"]))
    return {c: {"runs": len(s), "median": round(statistics.median(s), 2), "max": max(s)}
            for c, s in sorted(runs.items())}


def waivers(rows: List[dict]) -> dict:
    """The `waiver` rows: `count`, the count per `kind` (sorted by name) and the `config` ones' notes, oldest first."""
    found = [r for r in rows if r.get("event") == "waiver"]
    kinds = Counter(str(r.get("kind", "?")) for r in found)
    return {"count": len(found), "kinds": dict(sorted(kinds.items())),
            "config": [f"{r.get('file', '')} {r.get('note', '')}".strip() for r in found if r.get("kind") == "config"]}


def report(roots: List[Path], days: int) -> dict:
    """The record of the repos `roots` are in (every repo without roots) over the last `days` days."""
    repos, narrow = scope(roots) if roots else (None, {})
    rows = window(days, repos, narrow)
    found = ended(rows)
    return {"days": days, "repos": sorted(repos) if repos is not None else "all", **tally(found.values()),
            "rules": by_rule(found), "skips": skips(rows), "seconds": seconds(rows), "waivers": waivers(rows),
            "errors": sum(1 for r in rows if r.get("event") == "error")}


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


def rule_rows(rules: List[dict]) -> List[str]:
    """The rule table as lines of aligned text: a header, then one row per rule, with the number columns
    right-aligned."""
    head = ("rule", "tool", "blocked", "fixed", "let through", "open", "fix rate")
    table = [head] + [(x["rule"], x["tool"], str(x["blocked"]), str(x["fixed"]), through_text(x), str(x["open"]),
                       percent(x["fix_rate"])) for x in rules]
    widths = [max(len(row[c]) for row in table) for c in range(len(head))]
    return ["  ".join(cell.rjust(w) if c in NUMBERS else cell.ljust(w) for c, (cell, w) in enumerate(zip(row, widths)))
            .rstrip() for row in table]


def skip_rows(skips: Dict[str, Dict[str, int]]) -> List[str]:
    """One line per tool in the skip counts (from `skips`): its total, then the count per kind of note."""
    return [f"  {tool}: {sum(k.values())} (" + ", ".join(f"{kind} {n}" for kind, n in k.items()) + ")"
            for tool, k in skips.items()]


def second_rows(checks: Dict[str, dict]) -> List[str]:
    """One line per check in the seconds (from `seconds`): median, longest and the number of runs."""
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
    if not (data["blocked"] or data["skips"] or data["seconds"] or data["errors"] or data["waivers"]["count"]):
        return f"broom: nothing recorded for {where} in the last {data['days']} days"
    asked = f"asked the user {data['asked']}, " if data["asked"] else ""
    out = [f"broom report: {where}, the last {data['days']} days",
           f"blocked {data['blocked']}, fixed {data['fixed']}, let through {data['let_through']}, "
           f"still open {data['open']}, {asked}fix rate {percent(data['fix_rate'])}"]
    sections = [("By rule (each finding counts once; fix rate is fixed over fixed plus let through):",
                 [f"  {row}" for row in rule_rows(data["rules"])] if data["rules"] else []),
                ("Skipped checks, by tool:", skip_rows(data["skips"])),
                ("Seconds per check:", second_rows(data["seconds"])),
                ("Self-waivers (changes that loosened the bar; shown, never blocked):", waiver_rows(data["waivers"]))]
    for title, rows in sections:
        out += ["", title, *rows] if rows else []
    if data["errors"]:
        out += ["", f"A hook failed and let the action through {data['errors']} time(s)."]
    return "\n".join(out)
