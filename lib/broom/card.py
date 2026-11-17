"""The limits card: the bar broom holds code to in a repo, told to Claude at session start so it learns the bar before
it writes, not from a block after. The numbers are the repo's own (`.broom.json` moves them), a smell the repo
turned off is left out, and it ends with where to ask broom for a repo's numbers. It is made from the cached
diagnosis and the config alone: no tool runs, since Claude's first turn waits for the session hook."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .config import repo_config, setting
from .measure import Limits
from .smells import RepoLimits

# The sized smells the card names: the smell, what it limits, and the unit when it isn't obvious.
SIZED = (("function_lines", "functions", " lines"), ("file_lines", "files", ""), ("params", "parameters", ""),
         ("nesting", "nesting", ""), ("complexity", "complexity", ""))
# The smells that block a change for being added, whatever the size, as the card says them.
ADDED = (("suppression", "a lint suppression without a reason"), ("swallowed_error", "a swallowed error"),
         ("commented_code", "commented-out code"))
LEAD = "broom's bar in this repo, for the code you write or touch: {}."
ACCEPT = 'A blocked finding passes fixed, or with `broom known --accept "<why>"`.'
ASK = ("For a repo's numbers ask broom before writing a script: `broom stats` (lines, tests, coverage, suppressions, "
       "TODOs, what changes most), `broom smells` (smells, ranked), `broom diagnose` (the whole repo, before a refactor), `broom "
       "report` (what was blocked, fixed and let through), `broom doctor` (tools).")


def smells_off(repo: Path) -> List[str]:
    """The smells the repo's .broom.json turns off."""
    off = repo_config(repo).get("smells_off")
    return [str(x) for x in off] if isinstance(off, list) else []


def size_clauses(code: Limits, off: List[str]) -> List[str]:
    """`functions up to 50 lines (blocked past 100)`, `files up to 400 (1000)` and so on for the sized smells not turned
    off: the first says what the number in brackets is."""
    out: List[str] = []
    for name, noun, unit in SIZED:
        if name not in off:
            soft, hard = code[name]
            out.append(f"{noun} up to {soft}{unit} ({'' if out else 'blocked past '}{hard})")
    return out


def listed(items: List[str]) -> str:
    """`a`, `a or b`, `a, b or c`."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def limits_card(repo: Path, diagnosis: dict) -> Optional[str]:
    """The card for a repo, or None when its diagnosis (doctor's, cached) finds no language or `smells` is off."""
    if not diagnosis.get("languages") or setting("smells", repo) == "off":
        return None
    off = smells_off(repo)
    sizes = size_clauses(RepoLimits(repo).code, off)
    added = [what for name, what in ADDED if name not in off]
    blocked = f"A change is {'also ' if sizes else ''}blocked when it adds {listed(added)}." if added else ""
    return " ".join(x for x in (LEAD.format(", ".join(sizes)) if sizes else "", blocked, ACCEPT, ASK) if x)
