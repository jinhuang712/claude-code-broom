"""Where broom's files and state live: the plugin, its defaults and its data directory; hook input and output;
and the small JSON files that carry state from one hook to the next."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

# Resolved from this file, not CLAUDE_PLUGIN_ROOT: that variable is set for hooks but not for `broom` run from Bash.
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
# Hooks get CLAUDE_PLUGIN_DATA; the fallback is the same directory Claude Code assigns broom@claude-code-broom,
# so `broom` run from Bash shares state (the known-issue list) with the hooks.
DATA_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".claude" / "plugins" / "data" / "broom-claude-code-broom")
DEFAULTS = PLUGIN_ROOT / "defaults"

def read_hook_input() -> dict:
    try:
        data = json.load(sys.stdin)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def read_jsonc(path: Path) -> dict:
    try:
        text = path.read_text()
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r'^\s*//.*$|(?<=[,{\[\s])//[^"\n]*$', "", text, flags=re.M)
        text = re.sub(r",(\s*[}\]])", r"\1", text)
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def session_dir(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    d = DATA_ROOT / "sessions" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def append_line(path: Path, text: str) -> None:
    with open(path, "a") as f:
        f.write(text + "\n")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def prune_dirs(root: Path, max_age_days: float) -> None:
    """Remove the directories in `root` not modified for `max_age_days`."""
    cutoff = time.time() - max_age_days * 86400
    for d in root.glob("*") if root.is_dir() else []:
        try:
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def prune_sessions(max_age_days: float = 7) -> None:
    prune_dirs(DATA_ROOT / "sessions", max_age_days)


def short_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]
