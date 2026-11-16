"""`broom compare` as text a person reads: headings with `#` and aligned tables, no colour, and last a line to quote.
The same data is the `--json` object."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from .compare import compare, signed
from .gate import display, note_text
from .state import say
from .statsview import table


def kind_lines(data: dict) -> List[str]:
    """Per kind of smell, before, after and the difference, with the total last."""
    total = data["summary"]["smells"]
    rows = [[r["smell"], r["before"], r["after"], signed(r["change"])] for r in data["kinds"]]
    return table(["smell", "before", "after", "change"],
                 rows + [["total", total["before"], total["after"], signed(total["change"])]])


def list_lines(rows: List[dict], top: int, key: str) -> List[str]:
    """The first `top` smells of the list `key` and how many more there are; the lists of smells in both versions
    (`shrank` and `grew`) add their size or count before and after."""
    sizes = key in ("shrank", "grew")
    shown = [[f"{r['file']}:{r['line']}", r["smell"], *([f"{r['before']} -> {r['after']}"] if sizes else []),
              r["text"]] for r in rows[:top]]
    head = ["where", "smell", *(["was -> now"] if sizes else []), "text"]
    out = table(head, shown, left=tuple(range(len(head))))
    return out + ([f"  ... and {len(rows) - top} more; `--json` lists them all"] if len(rows) > top else [])


def hotspot_lines(data: dict) -> List[str]:
    """How each hotspot of the base moved: the smells past the hard limit and the hints, before -> after."""
    def moves(r: dict, key: str) -> str:
        return f"{r[key]['before']} -> {r[key]['after']}"

    rows = [[r["file"] + (f" (now {r['now']})" if r["now"] != r["file"] else ""), moves(r, "severe"),
             moves(r, "hints"), r["changes"], r["status"]] for r in data["hotspots"]]
    return table(["file", "past the hard limit", "hints", "changes then", "now"], rows, left=(0, 4))


def not_comparable_lines(data: dict) -> List[str]:
    """What was left out because a tool ran in one measuring and not in the other."""
    skip = data["not_comparable"]
    if not skip["tools"]:
        return []
    return ["", "## Not comparable",
            f"  A note says {', '.join(skip['tools'])} ran in one measuring and not in the other, so what it finds",
            f"  is left out of everything above: {', '.join(skip['kinds']) or 'nothing was found by it'}."]


def note_lines(data: dict) -> List[str]:
    """The notes of the two measurings, one line each."""
    return [f"note: {n}" if not n.startswith("missing:") else f"note: missing tool {note_text(n)}"
            for n in data["notes"]]


def render(data: dict, top: int) -> str:
    """The report for `data` (from `compare`): the kinds, the smells gone, new, smaller and bigger, the hotspots of
    the base, what couldn't be compared, and last the line to quote."""
    base = f"{data['base']} ({data['base_commit'][:7]})"
    out = [f"# broom compare: {display(Path(data['repo']))}, now against {base}", "", "## Smells by kind",
           *kind_lines(data)]
    for title, key in (("Gone", "gone"), ("New", "new"), ("Smaller", "shrank"), ("Bigger", "grew")):
        out += ["", f"## {title} ({len(data[key])})", *(list_lines(data[key], top, key) or ["  none"])]
    out += ["", f"## Hotspots of {data['base']}", *(hotspot_lines(data) or ["  none"])]
    out += not_comparable_lines(data) + note_lines(data)
    return "\n".join(out + ["", f"broom compare took {data['seconds']} s", data["quote"]])


def run(repo: Path, args: argparse.Namespace) -> int:
    """Compare the repo now with its state at `args.base`, as text or as JSON with `--json`."""
    data = compare(repo, args.base, args.top)
    say(json.dumps(data, indent=1) if args.json else render(data, args.top))
    return 0
