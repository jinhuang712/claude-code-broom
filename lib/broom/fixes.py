"""The usual fix of each code smell, one sentence each: the one home of those lines. They come from
defaults/fixes.json and reach Claude in three places: the block messages, the notes given as commit context, and
`broom fixes`, which the clean skill calls. A smell without a line gets none; a test keeps the file whole."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, Iterable, List

from .state import DEFAULTS, load_json

NOT_A_FIX = "Not a fix: a function cut in two at an arbitrary line, a new lint suppression, a looser .broom.json."


@lru_cache(maxsize=None)
def fixes() -> Dict[str, str]:
    """Each smell's name and its usual fix; empty when the file can't be read, so a block message still goes out."""
    data = load_json(DEFAULTS / "fixes.json", {})
    return {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else {}


def fix_lines(kinds: Iterable[str]) -> List[str]:
    """`  kind: fix` for each of `kinds` that has a fix line, in the order given."""
    known = fixes()
    return [f"  {k}: {known[k]}" for k in kinds if k in known]


def how_to_fix(kinds: Iterable[str]) -> List[str]:
    """The "How to fix:" block of a block message for the smell `kinds` found, with what is not a fix; no lines
    when none of them has a fix line."""
    lines = fix_lines(dict.fromkeys(kinds))
    return ["How to fix:", *lines, NOT_A_FIX] if lines else []


def answer(names: List[str], *, as_json: bool = False) -> str:
    """What `broom fixes` prints: the fix of each smell in `names` (all when empty), as lines or JSON. An unknown
    name ends the command with the list of names."""
    known = fixes()
    unknown = [n for n in names if n not in known]
    if unknown:
        raise SystemExit(f"broom: unknown smell {', '.join(unknown)}; the names are: {', '.join(known)}")
    picked = {n: known[n] for n in names or known}
    return json.dumps(picked, indent=1) if as_json else "\n".join(f"{n}: {line}" for n, line in picked.items())
