"""Keeps a test run out of the user's own data directory.

broom fixes its data directory when its modules are imported, so support.py imports this file first: it points
CLAUDE_PLUGIN_DATA at a directory the run owns, and every module then derives its paths from that. A guard on
writes backs that up, so a path that still reaches the user's directory is refused and the test that tried it fails.
A test that needs a clean state gets a directory of its own through `repoint`."""

from __future__ import annotations

import atexit
import importlib
import os
import pkgutil
import shutil
import sys
import tempfile
import traceback
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BROOM = ROOT / "bin" / "broom"
DEFAULT_DATA = Path.home() / ".claude" / "plugins" / "data" / "broom-claude-code-broom"
# What no test may write: the directory broom falls back to, and the one the person's environment names.
REAL_ROOTS = tuple({str(p) for d in (DEFAULT_DATA, os.environ.get("CLAUDE_PLUGIN_DATA")) if d
                    for p in (Path(d), Path(d).resolve())})
OPEN_FOR_WRITING = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
# The audit events that change a path, and which of their arguments are the paths.
CHANGES = {"os.mkdir": (0,), "os.remove": (0,), "os.rmdir": (0,), "os.rename": (0, 1), "os.truncate": (0,),
           "os.chmod": (0,), "os.chown": (0,), "os.utime": (0,), "os.symlink": (1,), "os.link": (1,),
           "shutil.rmtree": (0,)}
VIOLATIONS: list = []


class RealDataWrite(AssertionError):
    """A test tried to write into the user's own data directory."""


def reaches_real(path) -> bool:
    """Whether `path` is the user's data directory or something in it."""
    try:
        p = os.path.abspath(os.fsdecode(path))
    except (TypeError, ValueError):  # a file descriptor
        return False
    return any(p == real or p.startswith(real + os.sep) for real in REAL_ROOTS)


def refuse(what: str) -> None:
    VIOLATIONS.append(f"{what}\n{''.join(traceback.format_stack(limit=8))}")
    raise RealDataWrite(f"a test may not write the user's data directory: {what}")


def writes(event: str, args: tuple) -> list:
    """The paths an audit event writes."""
    if event == "open":
        return args[:1] if isinstance(args[2], int) and args[2] & OPEN_FOR_WRITING else []
    return [args[i] for i in CHANGES.get(event, ())]


def audit(event: str, args: tuple) -> None:
    """The guard: refuse a write to the user's data directory, and a broom started without a data directory of its
    own. It raises where the write is tried, and keeps a record for the test, since broom swallows some errors."""
    for path in writes(event, args):
        if reaches_real(path):
            refuse(f"{event} {path}")
    if event == "subprocess.Popen" and args[3] is not None and str(BROOM) in str(args[1]):
        if reaches_real(args[3].get("CLAUDE_PLUGIN_DATA", DEFAULT_DATA)):
            refuse(f"{BROOM.name} started without a CLAUDE_PLUGIN_DATA of its own")


def take_violations() -> list:
    """The writes refused since the last call."""
    found = VIOLATIONS[:]
    VIOLATIONS.clear()
    return found


def start() -> Path:
    """Give this run its own data directory, before broom is imported, and guard the user's."""
    sys.path.insert(0, str(ROOT / "lib"))
    if "broom.state" in sys.modules:
        raise RuntimeError("broom was imported before tests/support.py: its data directory is already fixed")
    root = Path(tempfile.mkdtemp(prefix="broom-test-data-")).resolve()
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    os.environ["CLAUDE_PLUGIN_DATA"] = str(root)
    sys.addaudithook(audit)
    return root


def data_paths(root: Path) -> list:
    """Every module-level path of broom's inside `root`, as (module, name, path relative to root): the data
    directory itself and what each module derived from it when it was imported."""
    for info in pkgutil.iter_modules(importlib.import_module("broom").__path__):
        importlib.import_module(f"broom.{info.name}")
    found = []
    for name, module in sorted(sys.modules.items()):
        if name == "broom" or name.startswith("broom."):
            found += [(module, attr, value.relative_to(root)) for attr, value in list(vars(module).items())
                      if isinstance(value, Path) and (value == root or root in value.parents)]
    return found


def repoint(paths: list, data: Path) -> ExitStack:
    """Move every path of `paths` under `data`, until the returned stack is closed."""
    stack = ExitStack()
    for module, attr, rel in paths:
        stack.enter_context(mock.patch.object(module, attr, data / rel))
    return stack


DATA = start()
PATHS = data_paths(DATA)
