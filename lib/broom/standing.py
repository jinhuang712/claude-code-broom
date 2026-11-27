"""Smells that stand in code no change touches, which the user decided to keep (decision 047).

`broom known --accept WHY --agreed --smell KIND FILE[:LINE]` records each of them in the known-issue store, with the
same record an accepted block leaves. Its key holds while the code it points at stays as it is (hotspots.standing_issue):
an occurrence is keyed by the text of its line, a sized smell by its message and the text of its first line.
`broom smells`, `broom diagnose` and the session note leave a known one out and say how many they left out.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import List, Optional, Tuple

from .gate import accept_allowed, baseline_add_entries, baseline_keys, checkout_path, display, issue_key
from .gitutil import git_root
from .hotspots import lines_of, repo_files, standing_issue
from .smell import Smell
from .smells import find_smells
from .state import say

Place = Tuple[Path, Optional[int]]  # a file or a folder, and a line in it or None for every line


def place(arg: str) -> Place:
    """A place as `broom known --smell` takes it: `FILE:LINE`, or a file or a folder alone."""
    path, colon, line = arg.rpartition(":")
    return (Path(path).resolve(), int(line)) if colon and line.isdigit() else (Path(arg).resolve(), None)


def at(s: Smell, line: int, places: List[Place]) -> bool:
    """Whether the smell `s` standing on `line` lies at one of `places`: in its file or folder, on its line when one
    is given."""
    return any((s.file == p or p in s.file.parents) and (n is None or n == line) for p, n in places)


def accept_standing(found: List[Smell], metric: str, places: List[Place], why: str) -> int:
    """Record the smells of kind `metric` among `found` that stand at `places` as known, with the reason and the
    user's agreement. Returns how many were not known before."""
    known = baseline_keys(s.file for s in found)
    entries = {}
    for s in found:
        for line in lines_of(s) if s.metric == metric else []:
            i = standing_issue(s, line)
            key = issue_key(i)
            if at(s, line, places) and key not in known:
                entries[key] = {"t": time.time(), "file": str(checkout_path(s.file)), "line": line, "tool": i.tool,
                                "rule": i.rule, "msg": i.msg, "why": why, "agreed": True}
    if entries:
        baseline_add_entries(entries)
    return len(entries)


def known_standing(args: argparse.Namespace) -> int:
    """Run `broom known --accept WHY --agreed --smell KIND PLACE...`: accept the smells of that kind standing at the
    places, with the user's agreement; 1 when none is there that isn't known already."""
    if not args.agreed:
        raise SystemExit("broom: a standing smell is accepted only with the user's agreement: ask them, then add "
                         "--agreed")
    if not accept_allowed():
        raise SystemExit("broom: accepting is off here (BROOM_NO_ACCEPT is set): fix the smell, or ask the user")
    why = (args.accept or "").strip()
    if not why or not args.paths:
        raise SystemExit('broom: say why and where: broom known --accept "<why>" --agreed --smell KIND FILE[:LINE]')
    places = [place(a) for a in args.paths]
    repo = git_root(places[0][0] if places[0][0].is_dir() else places[0][0].parent)
    if repo is None:
        raise SystemExit("broom: not inside a git repository")
    found, notes = find_smells(repo, repo_files(repo, [p for p, _ in places]), None)
    n = accept_standing(found, args.smell, places, why)
    if not n:
        where = " ".join(args.paths)
        say(f"broom: no {args.smell} that isn't known already at {where}: `broom smells --only {args.smell}` lists "
            f"them" + "".join(f"\nnote: {note}" for note in notes))
        return 1
    say(f"broom: accepted {n} standing {args.smell} smell(s) in {display(repo)} as known ({why}); `broom smells` "
        "leaves them out until their code changes")
    return 0
