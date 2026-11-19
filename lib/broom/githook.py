"""git's own pre-commit hook, for the commits Claude Code's commit hook never sees: a wrapper script's (one that
commits for you, so the Bash command holds no `git commit`) or a person's. `broom install-hook` adds it; it runs
`broom hook pre-commit`, which checks the staged files the way the Claude Code hook does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from .gitutil import git
from .state import PLUGIN_ROOT

MARK = "Added by `broom install-hook`"
OWN = f"#!/bin/sh\n# {MARK}"  # how a hook that is broom's own starts: only such a file is ever written over
MARKETPLACE_BROOM = '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/marketplaces/claude-code-broom/bin/broom"'
# Where a hook looks for broom: the marketplace's copy, which Claude Code keeps up to date, else this install, else
# broom from the PATH.
CANDIDATES = f'{MARKETPLACE_BROOM} "{PLUGIN_ROOT}/bin/broom" "$(command -v broom 2>/dev/null)"'
RUNS = '[ -n "$broom" ] && [ -x "$broom" ] && "$broom" hook pre-commit --help >/dev/null 2>&1'
# The one line for another tool's hook. It finds broom as `script` does, stops the commit only when broom finds
# something, lets the rest of that hook run, and ends in MARK, which is how `installed` knows it is there.
LINE = (f'for broom in {CANDIDATES}; do {RUNS} || continue; "$broom" hook pre-commit || exit 1; break; done'
        f"  # {MARK}")


def script() -> str:
    """The marketplace's copy, which Claude Code keeps up to date, else this install, else broom from the PATH.
    One too old for git's hook (its `hook --help` rejects `pre-commit`) is passed over; with none, the commit goes
    ahead."""
    return f"""{OWN}: check staged changes the way broom's Claude Code commit hook does, for the commits
# that hook doesn't see: a wrapper script's, a person's.
for broom in {CANDIDATES}; do
  {RUNS} && exec "$broom" hook pre-commit
done
exit 0
"""


def hook_path(repo: Path) -> Path:
    """Where git looks for `repo`'s pre-commit hook (core.hooksPath included)."""
    return repo / (git(["rev-parse", "--git-path", "hooks"], repo) or ".git/hooks").strip() / "pre-commit"


def installed(repo: Path) -> bool:
    """Whether `repo`'s git pre-commit hook runs broom, which checks what a commit really takes: broom's own hook, or
    another tool's with broom's line in it."""
    try:
        return MARK in hook_path(repo).read_text(errors="replace")
    except OSError:
        return False


def install(repo: Path) -> Tuple[bool, Path]:
    """Write the hook where git looks for hooks (core.hooksPath included), over broom's own but never over
    another tool's, with broom's line in it or not. Whether it was written, and where it is or would be."""
    path = hook_path(repo)
    hooks = path.parent
    if path.exists() and not path.read_text(errors="replace").startswith(OWN):
        return False, path
    hooks.mkdir(parents=True, exist_ok=True)
    path.write_text(script())
    path.chmod(0o755)
    return True, path
