"""`broom diagnose` as text a person reads: headings with `#` and aligned tables, so it reads as plain text and as
Markdown, no colour. The stats sections are those `broom stats` prints. The same data is the `--json` object."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from .dependencies import lines as dependency_lines
from .diagnose import diagnose
from .gate import display
from .hotspots import order_text
from .needs import LANG_NAMES
from .state import say
from .statsview import history_lines, rot_lines, size_lines, table, tests_lines
from .vulnerabilities import lines as vulnerability_lines


def heading(title: str, body: List[str]) -> List[str]:
    """A `##` heading over `body`, after a blank line; nothing under it says so."""
    return ["", f"## {title}", *(body or ["  none"])]


def summary_lines(data: dict) -> List[str]:
    """The counts, then each tool that was missing, then the notes: counts without a tool read as cleaner than the
    code is, so the tools come before any table."""
    s = data["summary"]
    rows = [("files read", s["files"]), ("code lines", s["lines"]), ("smells", s["smells"]),
            ("past the hard limit", s["severe"]), ("hints", s["hints"]), ("nits", s["nits"])]
    rows += [("accepted as known, collapsed", s["known"])] if s.get("known") else []
    width = max(len(name) for name, _ in rows)
    out = [f"  {name.ljust(width)}  {value}" for name, value in rows]
    if data["missing_tools"]:
        out += ["", "  Not all measured: these tools were missing, so the counts are lower than the code's:"]
        out += [f"    {tool}" for tool in data["missing_tools"]]
    return out + [f"  note: {n}" for n in data["notes"]]


def kind_lines(data: dict) -> List[str]:
    """Smells by kind: how many, how many past the hard limit, and the worst one."""
    rows = [[r["smell"], r["count"], r["severe"], f"{r['worst']['file']}:{r['worst']['line']}  {r['worst']['text']}"]
            for r in data["by_smell"]]
    return table(["smell", "count", "past the hard limit", "worst"], rows, left=(0, 3))


def language_lines(data: dict) -> List[str]:
    """Smells by language."""
    return table(["language", "count", "past the hard limit", "hints", "nits"],
                 [[LANG_NAMES.get(r["language"], r["language"]), r["count"], r["severe"], r["hints"], r["nits"]]
                  for r in data["by_language"]])


def hotspot_lines(data: dict) -> List[str]:
    """The hotspot files with their smells, changes and score, under the line that says how they are ordered."""
    rows = [[f["file"], f["severe"], f["hints"], f["nits"], f["changes"], f["score"]] for f in data["hotspots"]]
    shown = table(["file", "past the hard limit", "hints", "nits", "changes", "score"], rows)
    return [f"  Ordered {order_text(data['by'], data['stats']['last_commits'])}.", *shown] if shown else []


def worst_lines(data: dict, top: int) -> List[str]:
    """The `top` worst smells, and how many more there are."""
    rows = [[f"{s['file']}:{s['line']}", s["smell"], s["text"]] for s in data["smells"][:top]]
    out = table(["where", "smell", "text"], rows, left=(0, 1, 2))
    more = len(data["smells"]) - top
    rest = f"  ... and {more} more; `broom smells --top {len(data['smells'])}` lists them all, `--only KIND` one kind"
    return out + ([rest] if more > 0 else [])


def change_of(row: dict) -> str:
    """How a check-up counter stands against the last check-up, in a word, and the files that added to it."""
    if row["now"] is None:
        return "not measured"
    if row["was"] is None:
        return ""
    if row["grew"]:
        return "grew" + (f" ({', '.join(row['files'])})" if row["files"] else "")
    return "fell" if row["now"] < row["was"] else "same"


def last_line(c: dict) -> str:
    """Which check-up the numbers are set against, or why there is none."""
    if c["narrowed"]:
        return "  Counted within the paths given: the last check-up is of the whole repo, so it isn't set against."
    return f"  Last check-up: {c['last']}" if c["last"] else "  No check-up has run here yet."


def checkup_lines(data: dict) -> List[str]:
    """The check-up's counters, each with its value now and at the last check-up, whether it grew or not."""
    c = data["checkup"]
    if c["off"]:
        return ["  off in this repo: `smells_off` in .broom.json holds `checkup`, or `smells` is off"]
    rows = [[r["label"], "-" if r["now"] is None else r["now"], "-" if r["was"] is None else r["was"], change_of(r)]
            for r in c["counters"]]
    return [last_line(c), *table(["counter", "now", "at the last check-up", "change"], rows, left=(0, 3))]


def duplicate_lines(data: dict, top: int) -> List[str]:
    """The tests that repeat one another, the `top` largest: both places and the lines they share."""
    rows = data["duplicate_tests"]
    if not rows:
        return ["  not measured: jscpd is missing"] if any(t.startswith("jscpd") for t in data["missing_tools"]) else []
    shown = table(["where", "also at", "lines"],
                  [[f"{r['file']}:{r['line']}", f"{r['other']}:{r['other_line']}", r["lines"]] for r in rows[:top]],
                  left=(0, 1))
    more = len(rows) - top
    return [f"  {len(rows)} place(s) where tests repeat one another; the checks on a change leave these out.", *shown,
            *([f"  ... and {more} more; `--top {len(rows)}` lists them all"] if more > 0 else [])]


def stats_sections(stats: dict) -> List[str]:
    """The four sections of `broom stats`, each under a `##` heading."""
    out: List[str] = []
    for lines in (size_lines(stats["size"]), tests_lines(stats["tests"]), rot_lines(stats["rot"]),
                  history_lines(stats["history"])):
        out += ["", f"## {lines[0]}", *lines[1:]]
    return out


def render(data: dict, top: int) -> str:
    """The report for `data` (from `diagnose`): the summary, the smells by kind and by language, the hotspots, the
    `top` worst smells, the check-up's counters, the tests that repeat one another, the four stats sections, and how long
    it took."""
    narrowed = f", narrowed to {', '.join(data['paths'])}" if data["paths"] else ""
    out = [f"# broom diagnose: {display(Path(data['repo']))}{narrowed}"]
    out += heading("Summary", summary_lines(data)) + heading("Smells by kind", kind_lines(data))
    out += heading("Smells by language", language_lines(data)) + heading("Hotspots by churn", hotspot_lines(data))
    out += heading("The worst smells", worst_lines(data, top)) + heading("Check-up", checkup_lines(data))
    out += heading("Duplicate tests", duplicate_lines(data, top))
    deps = data["dependencies"]
    out += heading("Dependencies", dependency_lines(deps) + vulnerability_lines(deps["vulnerabilities"]))
    out += stats_sections(data["stats"])
    return "\n".join(out + ["", f"broom diagnose took {data['summary']['seconds']} s"])


def run(repo: Path, args: argparse.Namespace) -> int:
    """Diagnose `repo`, narrowed to `args.paths`, as text or as JSON with `--json`: printed, or written to `--out`
    with one line saying where."""
    data = diagnose(repo, [Path(p).resolve() for p in args.paths], args.top, args.commits,
                    vulnerabilities=args.vulnerabilities)
    text = json.dumps(data, indent=1) if args.json else render(data, args.top)
    if not args.out:
        say(text)
        return 0
    target = Path(args.out).resolve()
    try:
        target.write_text(text + "\n")
    except OSError as e:
        raise SystemExit(f"broom: can't write {args.out}: {e.strerror}")
    say(f"broom: wrote the diagnosis of {display(repo)} to {display(target)} in {data['summary']['seconds']} s")
    return 0
