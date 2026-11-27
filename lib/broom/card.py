"""The limits card: the bar broom holds code to in a repo, told to Claude at session start so it learns the bar before
it writes, not from a block after. The numbers are the repo's own (`.broom.json` moves them), a smell the repo
turned off is left out, and it ends with where to ask broom for a repo's numbers. It is made from the cached
diagnosis and the config alone: no tool runs, since Claude's first turn waits for the session hook."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .config import repo_config, setting
from .smells import RepoLimits

# The sized smells the card names: the smell, what it limits, and the unit when it isn't obvious.
SIZED = (("function_lines", "functions", " lines"), ("file_lines", "files", ""), ("params", "parameters", ""),
         ("nesting", "nesting", ""), ("complexity", "complexity", ""))
# The smells that block a change for being added, whatever the size, as the card says them.
ADDED = (("suppression", "a lint suppression without a reason"), ("swallowed_error", "a swallowed error"),
         ("commented_code", "commented-out code"))
LEAD = "broom's bar in this repo, for the code you write or touch: {}."
# What a length counts (decision 039), said where a length is named, so nobody saves lines by leaving comments out.
LENGTHS = ("function_lines", "file_lines")
CODE_LINES = "A length counts code lines: comment lines and blank lines are free."
# Decision 051: a test file's shape stops nothing.
IN_TESTS = "In test files only a skipped test, a broad assertion, a swallowed error and a suppression stop a change."
ACCEPT = ('A commit and a turn\'s end stop on code past the first number, as on most smells a change adds, until it '
          'is fixed or accepted with `broom known --accept "<why>"`: trying again passes nothing. If the user must '
          'decide, `broom known --ask "<question>"` and stop. Code already past its hard limit can\'t grow.')
TESTS = ("Run the project's tests after your last change to code: where a repo has tests, a turn's end stops without "
         "that.")
ASK = ("For a repo's numbers ask broom before writing a script: `broom stats` (lines, tests, coverage, suppressions, "
       "TODOs, what changes most), `broom smells` (smells, ranked; `--only "
       "function_lines` for the longest functions), `broom diagnose` (the whole repo: with those, dead code, missing "
       "doc comments, calls to deprecated APIs, duplicate tests and unused dependencies), `broom report` (what was "
       "blocked, fixed and let through), `broom doctor` (tools).")


def smells_off(repo: Path) -> List[str]:
    """The smells the repo's .broom.json turns off."""
    off = repo_config(repo).get("smells_off")
    return [str(x) for x in off] if isinstance(off, list) else []


def size_clauses(lim: RepoLimits, off: List[str]) -> List[str]:
    """`functions up to 50 lines (hard limit 100)`, `files up to 400 (1000)` and so on for the sized smells not turned
    off: the first says what the number in brackets is. A limit that differs for test files follows the code's, as
    `test files up to 800 (2000)`."""
    out: List[str] = []
    for name, noun, unit in SIZED:
        for kind, pair in (("", lim.code[name]), ("test ", lim.test[name])):
            if name not in off and (not kind or pair != lim.code[name]):
                out.append(f"{kind}{noun} up to {pair[0]}{unit} ({'' if out else 'hard limit '}{pair[1]})")
    return out


def listed(items: List[str]) -> str:
    """`a`, `a or b`, `a, b or c`."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def limits_card(repo: Path, diagnosis: dict) -> Optional[str]:
    """The card for a repo, or None when its diagnosis (doctor's, cached) finds no language or `smells` is off."""
    if not diagnosis.get("languages") or setting("smells", repo) == "off":
        return None
    off = smells_off(repo)
    sizes = size_clauses(RepoLimits(repo), off)
    added = [what for name, what in ADDED if name not in off]
    blocked = f"A change is {'also ' if sizes else ''}blocked when it adds {listed(added)}." if added else ""
    free = "" if set(LENGTHS) <= set(off) else CODE_LINES
    lead = LEAD.format(", ".join(sizes)) if sizes else ""
    return " ".join(x for x in (lead, free, blocked, IN_TESTS, ACCEPT, TESTS, ASK) if x)
