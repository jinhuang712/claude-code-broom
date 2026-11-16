"""`broom diagnose` as text a person reads: headings with `#` and aligned tables, so it reads as plain text and as
Markdown, no colour. The stats sections are those `broom stats` prints. The same data is the `--json` object."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from .diagnose import diagnose
from .gate import display
from .hotspots import HOTSPOTS_TITLE
from .state import say
from .statsview import history_lines, rot_lines, size_lines, table, tests_lines


def heading(title: str, body: List[str]) -> List[str]:
    """A `##` heading over `body`, after a blank line; nothing under it says so."""
    return ["", f"## {title}", *(body or ["  none"])]


def summary_lines(data: dict) -> List[str]:
    """The counts, then each tool that was missing, then the notes: counts without a tool read as cleaner than the
    code is, so the tools come before any table."""
    s = data["summary"]
    rows = [("files read", s["files"]), ("lines (non-blank)", s["lines"]), ("smells", s["smells"]),
            ("past the hard limit", s["severe"]), ("hints", s["hints"])]
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
    return table(["language", "count", "past the hard limit", "hints"],
                 [[r["language"], r["count"], r["severe"], r["hints"]] for r in data["by_language"]])


def hotspot_lines(data: dict) -> List[str]:
    """The hotspot files with their smells, changes and score, under the line that says how they are ordered."""
    rows = [[f["file"], f["severe"], f["hints"], f["changes"], f["score"]] for f in data["hotspots"]]
    shown = table(["file", "past the hard limit", "hints", "changes", "score"], rows)
    return [f"  {HOTSPOTS_TITLE[data['by']]}", *shown] if shown else []


def worst_lines(data: dict, top: int) -> List[str]:
    """The `top` worst smells, and how many more there are."""
    rows = [[f"{s['file']}:{s['line']}", s["smell"], s["text"]] for s in data["smells"][:top]]
    out = table(["where", "smell", "text"], rows, left=(0, 1, 2))
    more = len(data["smells"]) - top
    return out + ([f"  ... and {more} more; `--json` lists them all"] if more > 0 else [])


def stats_sections(stats: dict) -> List[str]:
    """The four sections of `broom stats`, each under a `##` heading."""
    out: List[str] = []
    for lines in (size_lines(stats["size"]), tests_lines(stats["tests"]), rot_lines(stats["rot"]),
                  history_lines(stats["history"])):
        out += ["", f"## {lines[0]}", *lines[1:]]
    return out


def render(data: dict, top: int) -> str:
    """The report for `data` (from `diagnose`): the summary, the smells by kind and by language, the hotspots, the
    `top` worst smells, the four stats sections, and how long it took."""
    narrowed = f", narrowed to {', '.join(data['paths'])}" if data["paths"] else ""
    out = [f"# broom diagnose: {display(Path(data['repo']))}{narrowed}"]
    out += heading("Summary", summary_lines(data)) + heading("Smells by kind", kind_lines(data))
    out += heading("Smells by language", language_lines(data)) + heading("Hotspots by churn", hotspot_lines(data))
    out += heading("The worst smells", worst_lines(data, top)) + stats_sections(data["stats"])
    return "\n".join(out + ["", f"broom diagnose took {data['summary']['seconds']} s"])


def run(repo: Path, args: argparse.Namespace) -> int:
    """Diagnose `repo`, narrowed to `args.paths`, as text or as JSON with `--json`: printed, or written to `--out`
    with one line saying where."""
    data = diagnose(repo, [Path(p).resolve() for p in args.paths], args.top, args.days)
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
