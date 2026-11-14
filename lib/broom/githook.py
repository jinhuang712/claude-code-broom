"""git's own pre-commit hook, for the commits Claude Code's commit hook never sees: a wrapper script's (one that
commits for you, so the Bash command holds no `git commit`) or a person's. `broom install-hook` adds it; it runs
`broom hook pre-commit`, which checks the staged files the way the Claude Code hook does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from .common import PLUGIN_ROOT, git

MARK = "Added by `broom install-hook`"
MARKETPLACE_BROOM = '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/marketplaces/claude-code-broom/bin/broom"'
LINE = f"{MARKETPLACE_BROOM} hook pre-commit || exit 1"


def script() -> str:
    """The marketplace's copy, which Claude Code keeps up to date, else this install, else broom from the PATH.
    One too old for git's hook (its `hook --help` rejects `pre-commit`) is passed over; with none, the commit goes
    ahead."""
    return f"""#!/bin/sh
# {MARK}: check staged changes the way broom's Claude Code commit hook does, for the commits
# that hook doesn't see: a wrapper script's, a person's.
for broom in {MARKETPLACE_BROOM} "{PLUGIN_ROOT}/bin/broom" "$(command -v broom 2>/dev/null)"; do
  [ -n "$broom" ] && [ -x "$broom" ] || continue
  "$broom" hook pre-commit --help >/dev/null 2>&1 && exec "$broom" hook pre-commit
done
exit 0
"""


def install(repo: Path) -> Tuple[bool, Path]:
    """Write the hook where git looks for hooks (core.hooksPath included), over broom's own but never over
    another tool's. Whether it was written, and where it is or would be."""
    hooks = repo / (git(["rev-parse", "--git-path", "hooks"], repo) or ".git/hooks").strip()
    path = hooks / "pre-commit"
    if path.exists() and MARK not in path.read_text(errors="replace"):
        return False, path
    hooks.mkdir(parents=True, exist_ok=True)
    path.write_text(script())
    path.chmod(0o755)
    return True, path
