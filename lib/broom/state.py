"""Where broom's files and state live: the plugin, its defaults and its data directory; hook input and output;
and the small JSON files that carry state from one hook to the next."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import select
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

# Resolved from this file, not CLAUDE_PLUGIN_ROOT: that variable is set for hooks but not for `broom` run from Bash.
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
# Hooks get CLAUDE_PLUGIN_DATA; the fallback is the same directory Claude Code assigns broom@claude-code-broom,
# so `broom` run from Bash shares state (the known-issue list) with the hooks.
DATA_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".claude" / "plugins" / "data" / "broom-claude-code-broom")
DEFAULTS = PLUGIN_ROOT / "defaults"

HOOK_INPUT_SECONDS = 10  # how long a hook waits for what Claude Code sends it, whether or not it closes its end


def read_hook_input(wait: float = HOOK_INPUT_SECONDS) -> dict:
    """The JSON object Claude Code sends a hook. It is read until it parses, not until the end of the input: a harness
    that doesn't close the pipe would otherwise keep the hook waiting until Claude Code gave up on it."""
    try:
        fd = sys.stdin.fileno()
    except (ValueError, OSError):  # not a real file: the launcher read the input already, and put it back
        try:
            data = json.load(sys.stdin)
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}
    buf = b""
    end = time.monotonic() + wait
    while True:
        try:
            data = json.loads(buf)
            return data if isinstance(data, dict) else {}
        except ValueError:
            pass  # not all of it yet
        left = end - time.monotonic()
        try:
            if left <= 0 or not select.select([fd], [], [], left)[0]:
                return {}
            chunk = os.read(fd, 65536)
        except (OSError, ValueError):
            return {}
        if not chunk:  # the end of the input: what there is, parsed or not
            try:
                data = json.loads(buf)
            except ValueError:
                return {}
            return data if isinstance(data, dict) else {}
        buf += chunk


def emit(obj: dict) -> None:
    """Write `obj` as one JSON object to stdout, with no newline after it, and flush: how a hook answers Claude Code."""
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def say(text: str = "") -> None:
    """Write `text` and a newline to stdout, as print does."""
    sys.stdout.write(f"{text}\n")


def warn(text: str) -> None:
    """Write `text` and a newline to stderr and flush it, so a hook that exits at once still shows it."""
    sys.stderr.write(f"{text}\n")
    sys.stderr.flush()


def parse_jsonc(text: str) -> dict:
    """The JSON object in `text`, which may hold comments and trailing commas; {} when it isn't one."""
    try:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r'^\s*//.*$|(?<=[,{\[\s])//[^"\n]*$', "", text, flags=re.M)
        text = re.sub(r",(\s*[}\]])", r"\1", text)
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def read_jsonc(path: Path) -> dict:
    """Parse the JSON-with-comments file at `path` into a dict; an unreadable or invalid file gives {}."""
    try:
        return parse_jsonc(path.read_text())
    except (OSError, ValueError):  # unreadable, or not text
        return {}


def session_dir(session_id: str) -> Path:
    """Return the data directory for a session, made if missing; an empty id uses "nosession"."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    d = DATA_ROOT / "sessions" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def append_line(path: Path, text: str) -> None:
    """Append `text` and a newline to the file at `path`, creating the file when it is missing."""
    with open(path, "a") as f:
        f.write(text + "\n")


def load_json(path: Path, default):
    """Load the JSON file at `path`, or give `default` when it is missing, unreadable or not JSON."""
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return default


def save_json(path: Path, data) -> None:
    """Write whole or not at all. The temporary file is this process's and thread's own: two writers at once used
    to share one, and the second to finish found it already renamed away."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


LOCK_WAIT = 5  # seconds; a lock held longer is taken for dead


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold an exclusive lock for `path`, so hooks that run at once take turns. A lock that can't be had, because the
    directory is read-only or because whoever holds it holds it for LOCK_WAIT seconds, is no lock: the change
    goes ahead, as it did before there were any. Waiting on it for good is how a hook would hang."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(f"{path}.lock", os.O_CREAT | os.O_RDWR)
    except OSError:
        yield
        return
    try:
        end = time.monotonic() + LOCK_WAIT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= end:
                    break
                time.sleep(0.01)
        yield
    finally:
        os.close(fd)


def update_json(path: Path, default, change: Callable) -> None:
    """Read `path`, let `change(data)` modify it in place (or return a new value), and write it back, all under
    the lock: two hooks reading, changing and writing at once no longer lose one another's change."""
    with locked(path):
        data = load_json(path, default)
        result = change(data)
        save_json(path, data if result is None else result)


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
    """Delete the session directories not touched for `max_age_days` days (7 by default), under the data root."""
    prune_dirs(DATA_ROOT / "sessions", max_age_days)


def short_hash(text: str) -> str:
    """Return the first 16 hex digits of the SHA-1 of `text`, a short id for keys and file names; not for security."""
    return hashlib.sha1(text.encode()).hexdigest()[:16]
