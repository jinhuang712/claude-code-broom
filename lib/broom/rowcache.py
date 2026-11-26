"""What the smell measurers found in a file's content, kept by that content, so a file is measured once
however often it is checked: the base of a change doesn't change from one try to the next, and a file the stop
gate checks again, still blocked, is the same text. Only a measurement that finished whole is kept: with a tool
missing or timed out, the rows are a part. A record stays until what decided it changes (the content, the limits, the
tools, broom's version) or until MAX_ENTRIES newer ones push it out; the stamp in it only orders them."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import __version__
from .measure import Limits, Raw, measure
from .state import DATA_ROOT, load_json, short_hash, update_json
from .toolchain import resolve_bin

ROWS = DATA_ROOT / "rows"
MAX_ENTRIES = 20000
MEASURE_TOOLS = ("ruff", "oxlint", "node", "golangci-lint", "swiftlint", "ast-grep")  # what the rows depend on
Measure = Callable[[Path, Dict[str, str], Limits, Path, List[str]], List[Raw]]


class RowCache:
    """The measured rows of one repo, kept on disk and reused for files whose text and tools are unchanged."""
    def __init__(self, repo: Path, limits: Limits, measuring: Optional[Measure] = None) -> None:
        self.repo, self.limits, self.measuring = repo, limits, measuring or measure
        self.path = ROWS / f"{short_hash(str(repo))}.json"
        self.lock = threading.Lock()
        self.entries: Dict[str, list] = load_json(self.path, {})
        self.changed = False
        # Where each tool is, so one that is gone or upgraded (a new path) gets its measurements made again, and a
        # missing one is said so, not hidden behind rows it measured before.
        tools = ",".join(resolve_bin(t, repo, repo) or "-" for t in MEASURE_TOOLS)
        self.bar = f"{__version__}\0{json.dumps(limits, sort_keys=True)}\0{tools}\0"

    def key(self, rel: str, text: str) -> str:
        """A cache key for `rel` at this text, also covering broom's version, the limits and the tools' paths."""
        return hashlib.sha1(f"{self.bar}{rel}\0{text}".encode()).hexdigest()

    def measure(self, root: Path, texts: Dict[str, str], notes: List[str]) -> List[Raw]:
        """The rows for `texts`, measuring only the files whose content hasn't been measured under these limits."""
        keys = {rel: self.key(rel, text) for rel, text in texts.items()}
        with self.lock:
            known = {rel: self.entries[k][1] for rel, k in keys.items() if k in self.entries}
        rows = [Raw(*row) for found in known.values() for row in found]
        todo = {rel: text for rel, text in texts.items() if rel not in known}
        if not todo:
            return rows
        local: List[str] = []
        fresh = self.measuring(root, todo, self.limits, self.repo, local)
        notes += local
        if not local:
            with self.lock:
                for rel in todo:
                    self.entries[keys[rel]] = [time.time(), [[r.rel, r.line, r.metric, r.key, r.value, r.tool, r.span]
                                                              for r in fresh if r.rel == rel]]
                self.changed = True
        return rows + fresh

    def save(self) -> None:
        """Add this run's rows to what is on disk now: another run may have added its own meanwhile."""
        if not self.changed:
            return

        def merge(on_disk: dict) -> dict:
            with self.lock:
                on_disk.update(self.entries)
            newest = sorted(on_disk.items(), key=lambda kv: kv[1][0], reverse=True)[:MAX_ENTRIES]
            return dict(newest)

        update_json(self.path, {}, merge)


def forget(repo: Path) -> None:
    """Drop the rows kept for `repo`, a path that won't come back (a temporary checkout), rather than leave them to
    pile up."""
    path = ROWS / f"{short_hash(str(repo))}.json"
    for f in (path, path.with_name(path.name + ".lock")):
        f.unlink(missing_ok=True)
