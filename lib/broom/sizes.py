"""The longest functions or types of a repo, past the soft limit or not: what `broom smells --only function_lines`
(or `type_lines`) lists after the smells when fewer than `--top` of them are smells, so "which are the longest?"
has an answer in a small repo. A size under the soft limit is no smell: it is measured here, apart from the smell
scan, and counted nowhere."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Tuple

from .config import repo_config
from .measure import Limits, Raw
from .maintained import Maintained
from .rowcache import RowCache
from .smell import level
from .smells import RepoLimits, counted, current_texts
from .toolchain import RS_EXTS

SIZED = ("function_lines", "type_lines")  # the kinds of smell whose sizes can be listed
LOWEST = 1  # the soft limit the tools measure under for a list of sizes: they report all that is longer than a line
NO_RUST = "Rust functions under the limit are not listed: clippy, which measures them, reports only smells"


def lowered(limits: Limits, metric: str) -> Limits:
    """`limits` with the soft limit of `metric` at LOWEST, so the tools report every function or type of that kind.
    The rows cache keeps rows by the limits they were measured under, so these are never served to a normal run, nor
    a normal run's rows to this one."""
    return {**limits, metric: (LOWEST, limits[metric][1])}


def find_sizes(repo: Path, files: List[Path], metric: str, count: int) -> Tuple[List[Raw], List[str]]:
    """The `count` longest of the kind `metric` ("function_lines" or "type_lines") in `files` that are under their
    soft limit, longest first, and the notes of the tools that didn't run or finished late. What is past the limit
    is a smell and `find_smells` has it."""
    lim = RepoLimits(repo)
    texts = current_texts(repo, files, Maintained(repo))
    notes = [NO_RUST] if metric == "function_lines" and any(f.suffix in RS_EXTS for f in files) else []
    if count <= 0 or not texts:
        return [], notes
    rows = RowCache(repo, lowered(lim.measured, metric))
    with tempfile.TemporaryDirectory(prefix="broom-sizes-") as tmp:
        measured = rows.measure(Path(tmp) / "now", texts, notes)
    rows.save()
    off = tuple(repo_config(repo).get("smells_off") or ())
    under = [r for r in counted(measured, off) if r.metric == metric and not level(r.value, lim.of(r.rel)[metric])]
    return sorted(under, key=lambda r: (-r.value, r.rel, r.line))[:count], list(dict.fromkeys(notes))
