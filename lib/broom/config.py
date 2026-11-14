"""Settings and the repo's .broom.json: what the user and the repo chose, the smell limits, and the globs that keep
paths out of everything or mark them as legacy."""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .gitutil import git, git_root
from .state import read_jsonc

SETTINGS = {
    "format_on": ("commit", ("commit", "edit", "off")),
    "check_on": ("stop", ("commit", "stop", "off")),
    "format_scope": ("changed", ("changed", "function", "file")),
    "smells": ("on", ("on", "off")),
}
# Code smell limits, (soft, hard): past soft is a hint, past hard a block. SwiftLint's own warning and error
# defaults, except nesting; .broom.json `limits` moves them per repo.
SMELL_LIMITS = {
    "function_lines": (50, 100),
    "file_lines": (400, 1000),
    "params": (5, 8),
    "nesting": (4, 6),
    "complexity": (10, 20),
    "nested_ternary": (0, 0),
    "type_lines": (250, 1_000_000),  # a hint only: whether to split a type is a design call
    "duplicate_lines": (10, 30),  # a block of code repeated elsewhere
}
# Code nothing uses, found across the repo (JS/TS/Python): a hint only, as dynamic loading looks unused too.
DEAD_CODE = "dead_code"
# Smells that count by occurrence, not by size: a change that adds one gets this level.
SMELL_PRESENCE = {
    "suppression": "block",  # a lint suppression without a reason or a rule
    "swallowed_error": "block",  # an empty block or catch, or a catch that only rethrows
    "commented_code": "block",
    "unused_params": "hint",
    "magic_numbers": "hint",
    "debug_output": "hint",
    "todo": "hint",
    "type_escape": "hint",  # any, force casts and unwraps, non-null assertions
    "globals": "hint",
    "bool_params": "hint",
    "broad_test_asserts": "hint",
}
PLUGIN_ID = "broom@claude-code-broom"


REPO_FILE = ".broom.json"


def repo_config(start: Optional[Path]) -> dict:
    """The repo's .broom.json, or {}. It holds only choices and path patterns, never commands, so honoring it in a
    repo you don't trust is safe."""
    if start is None:
        return {}
    root = git_root(start if start.is_dir() else start.parent)
    if root is None:
        return {}
    if root not in _repo_configs:
        path = repo_file(root)
        _repo_configs[root] = read_jsonc(path) if path else {}
    return _repo_configs[root]


def repo_file(root: Path) -> Optional[Path]:
    """The .broom.json a repo reads: at its git root, else, in a linked worktree that has none, the main worktree's.
    A .broom.json that git ignores (a global `**/.broom.json`, say) never reaches a new worktree, which then ran
    with broom's defaults instead of the repo's limits and excludes."""
    if (root / REPO_FILE).is_file():
        return root / REPO_FILE
    common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], root)
    main = Path(common.strip()).parent if common else None
    return main / REPO_FILE if main and main != root and (main / REPO_FILE).is_file() else None


_repo_configs: Dict[Path, dict] = {}


def setting(name: str, start: Optional[Path] = None) -> str:
    return setting_source(name, start)[0]


def setting_source(name: str, start: Optional[Path] = None) -> Tuple[str, str]:
    """A setting and where it came from (`repo`, `user` or `default`): the repo's .broom.json first (like IDE
    project settings over IDE defaults), then the plugin's userConfig. Claude Code exports userConfig to hooks as
    CLAUDE_PLUGIN_OPTION_<NAME> but not to commands run through Bash, so `broom` there reads it where Claude Code
    stores it, in the user settings file."""
    default, allowed = SETTINGS[name]
    repo_value = str(repo_config(start).get(name, "")).strip().lower()
    if repo_value in allowed:
        return repo_value, "repo"
    value = os.environ.get(f"CLAUDE_PLUGIN_OPTION_{name.upper()}")
    if value is None:
        config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"
        try:
            options = json.loads(config.read_text()).get("pluginConfigs", {}).get(PLUGIN_ID, {}).get("options", {})
            value = str(options.get(name, ""))
        except (OSError, ValueError, AttributeError):
            value = ""
    value = value.strip().lower()
    return (value, "user") if value in allowed else (default, "default")

def excluded(path: Path) -> bool:
    """Whether the repo's .broom.json `exclude` globs (relative to the git root) cover this file."""
    root = git_root(path.parent)
    return root is not None and not drop_excluded(root, [path.resolve()])


def glob_matcher(patterns: object) -> Callable[[str], bool]:
    """Whether a path relative to the git root matches one of .broom.json's globs (`exclude`, `legacy`); `**/x`
    matches `x` at the root too."""
    globs = [str(p) for p in patterns] if isinstance(patterns, list) else []
    globs += [g[3:] for g in globs if g.startswith("**/")]
    return lambda rel: any(fnmatch.fnmatch(rel, g) for g in globs)


def drop_excluded(root: Path, files: List[Path]) -> List[Path]:
    """`files` (resolved paths) minus those the .broom.json `exclude` globs of the repo at `root` cover; one read
    of the config for the lot, where `excluded` finds each file's repo."""
    patterns = repo_config(root).get("exclude")
    if not patterns:
        return files
    matches = glob_matcher(patterns)
    out = []
    for f in files:
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            out.append(f)
            continue
        if not matches(rel):
            out.append(f)
    return out
