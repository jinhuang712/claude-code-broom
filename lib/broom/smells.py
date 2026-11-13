"""Code smells, of two kinds. Sized ones (long functions, files and types, many parameters, deep nesting, high
complexity) have a soft and a hard limit; the rest count by occurrence (suppressions without a reason,
swallowed errors, commented-out code, magic numbers, TODOs, type escapes, and so on) at a fixed level.

They are measured against broom's own limits, apart from the project's lint config, so one bar holds in every
repo; `.broom.json` can move it. Only what a change made worse counts: each file is measured as it is and as it
was at the base revision. A sized smell counts when the change pushed it past a limit, or grew it while past
the hard one; an occurrence counts when the change added it. Legacy code a change leaves as it was never comes
up.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .checks import Issue
from .common import SMELL_LIMITS, SMELL_PRESENCE, repo_config, setting
from .gate import issue_key
from .measure import SMELL_EXTS, Limits, Raw, measure

# Dependencies, environments and build output, which nobody here maintains, and generated code.
SKIP_DIRS = {
    "node_modules", "vendor", "Pods", "Carthage", ".venv", "venv", "site-packages", "__pycache__",
    ".build", "DerivedData", "dist", "build", "out", "release", "target", ".bundle", ".next", "coverage",
    "test-results", "testdata", "Generated", "generated",
}
GENERATED = re.compile(r"DO NOT EDIT|@generated")
TEST_FILE = re.compile(r"(^|/)(tests?|__tests__|Tests)/|_test\.(go|py)$|(^|/)test_[^/]*\.py$|"
                       r"\.(test|spec)\.[cm]?[jt]sx?$|Tests?\.swift$")
TEST_BLOCK = re.compile(r"(describe|it|test|suite|context)(\.\w+)?\(")
GIT_TIMEOUT = 60

DESCRIBE = {
    "function_lines": "{key} is {value} lines long",
    "file_lines": "the file is {value} lines long",
    "params": "{key} takes {value} parameters",
    "nesting": "blocks nest {value} levels deep",
    "complexity": "{key} has complexity {value}",
    "nested_ternary": "a ternary nests inside another",
    "type_lines": "{key} is {value} lines long",
}
LABELS = {
    "suppression": "lint suppression(s) without a reason or rule",
    "swallowed_error": "empty block(s) or swallowed error(s)",
    "commented_code": "line(s) of commented-out code",
    "unused_params": "unused parameter(s)",
    "magic_numbers": "magic number(s)",
    "debug_output": "debug print(s)",
    "todo": "TODO/FIXME comment(s)",
    "type_escape": "type escape(s): any, force casts or unwraps, non-null assertions",
    "globals": "global statement(s)",
    "bool_params": "boolean flag parameter(s)",
    "broad_test_asserts": "too broad test assertion(s)",
}
HINTS_SHOWN = 10
LINES_SHOWN = 5


@dataclass
class Smell:
    repo: Path
    file: Path
    line: int
    metric: str
    key: str
    value: int  # the size, or for an occurrence smell the count in the file
    was: Optional[int]
    tool: str
    level: str  # "hint" past the soft limit, "block" past the hard one
    limit: int
    added: List[int] = field(default_factory=list)  # an occurrence smell's lines this change added

    def text(self) -> str:
        if self.metric in SMELL_PRESENCE:
            where = ", ".join(map(str, self.added[:LINES_SHOWN])) + (" ..." if len(self.added) > LINES_SHOWN else "")
            if self.was is None:
                return f"{self.value} {LABELS[self.metric]} at line(s) {where}"
            return (f"{self.value - self.was} more {LABELS[self.metric]} ({self.value} in the file, was {self.was}); "
                    f"new or changed at line(s) {where}")
        what = DESCRIBE[self.metric].format(key=self.key, value=self.value)
        bar = f"hard limit {self.limit}" if self.level == "block" else f"over {self.limit}"
        how = "new" if self.was is None else f"was {self.was}"
        return f"{what} ({bar}; {how})"

    def issue(self) -> Issue:
        return Issue("smells", self.repo, self.file, self.line, 0, self.metric, self.text(),
                     severe=self.level == "block")


def limits(repo: Path) -> Limits:
    """broom's limits, with any the repo's .broom.json `limits` sets: {"function_lines": [50, 100], ...}."""
    merged = dict(SMELL_LIMITS)
    for name, pair in (repo_config(repo).get("limits") or {}).items():
        if name in merged and isinstance(pair, list) and len(pair) == 2 and all(isinstance(n, int) for n in pair):
            merged[name] = (pair[0], pair[1])
    return merged


# ---------------------------------------------------------------- comparing versions


LEVELS = ("", "hint", "block")


def level(value: int, limit: Tuple[int, int]) -> str:
    soft, hard = limit
    return "block" if value > hard else "hint" if value > soft else ""


def made_worse(value: int, old: Optional[int], limit: Tuple[int, int]) -> bool:
    """Pushed past a limit, or grown while past the hard one. Growth below that is noise: a 600-line file that
    gains a line was already over 400, and saying so on every edit teaches Claude to ignore broom."""
    was = level(old, limit) if old is not None else ""
    now = level(value, limit)
    return LEVELS.index(now) > LEVELS.index(was) or (now == "block" and old is not None and value > old)


def noise(r: Raw) -> bool:
    """Findings that measure the tool, not the code: in tests, complexity counts every assertion's `if` and magic
    numbers are the fixtures; a test framework's describe/it callbacks are containers, long by nature."""
    if r.metric in ("complexity", "magic_numbers") and TEST_FILE.search(r.rel):
        return True
    return r.metric in ("function_lines", "complexity") and bool(TEST_BLOCK.match(r.key))


def compare_sizes(now: List[Raw], before: Optional[List[Raw]], lim: Limits, repo: Path) -> List[Smell]:
    was = {(r.rel, r.metric, r.key): r.value for r in before or []}
    out = []
    for r in now:
        old = was.get((r.rel, r.metric, r.key))
        at = level(r.value, lim[r.metric])
        if at and (before is None or made_worse(r.value, old, lim[r.metric])):
            limit = lim[r.metric][1] if at == "block" else lim[r.metric][0]
            out.append(Smell(repo, repo / r.rel, r.line, r.metric, r.key, r.value, old, r.tool, at, limit))
    return out


def one_per_line(rows: List[Raw]) -> List[Raw]:
    """A line counts once per smell: nolintlint reports one `//nolint` up to three times, one per rule it breaks."""
    seen = {(r.rel, r.metric, r.line): r for r in rows}
    return sorted(seen.values(), key=lambda r: (r.rel, r.line))


def compare_occurrences(now: List[Raw], before: Optional[List[Raw]], repo: Path) -> List[Smell]:
    """Per file and smell, the lines the change added, matched by text against the base: a moved line stays old,
    an edited one is new."""
    now = one_per_line(now)
    before = None if before is None else one_per_line(before)
    old = Counter((r.rel, r.metric, r.key) for r in before or [])
    added: Dict[Tuple[str, str], List[Raw]] = {}
    for r in now:
        if old[(r.rel, r.metric, r.key)] > 0:
            old[(r.rel, r.metric, r.key)] -= 1
        else:
            added.setdefault((r.rel, r.metric), []).append(r)
    total = Counter((r.rel, r.metric) for r in now)
    was = Counter((r.rel, r.metric) for r in before or [])
    # An edited line that keeps its occurrence is new by text but adds nothing: only a higher count counts.
    return [Smell(repo, repo / rel, rows[0].line, metric, metric, total[(rel, metric)],
                  None if before is None else was[(rel, metric)], rows[0].tool, SMELL_PRESENCE[metric], 0,
                  [r.line for r in rows])
            for (rel, metric), rows in added.items() if before is None or total[(rel, metric)] > was[(rel, metric)]]


def compare(now: List[Raw], before: Optional[List[Raw]], lim: Limits, repo: Path,
            off: Tuple[str, ...] = ()) -> List[Smell]:
    """`before` is None to report every finding (a whole-repo sweep), else the base version's findings. `off`
    names smells the repo turned off."""
    kept = [r for r in now if r.metric not in off and not noise(r)]
    sizes = [r for r in kept if r.metric not in SMELL_PRESENCE]
    found = (compare_sizes(sizes, before, lim, repo)
             + compare_occurrences([r for r in kept if r.metric in SMELL_PRESENCE],
                                   None if before is None else [r for r in before if r.metric in SMELL_PRESENCE],
                                   repo))
    return sorted(found, key=lambda s: (s.level != "block", str(s.file), s.line))


def maintained(rel: str) -> bool:
    """Code someone here maintains, by its path: not a dependency, build output or minified file."""
    return not (SKIP_DIRS & set(rel.split("/")[:-1]) or rel.endswith((".min.js", ".d.ts")))


def current_texts(repo: Path, files: List[Path]) -> Dict[str, str]:
    """The files' text, leaving out what nobody maintains here: decided by path before any file is read, then
    generated code by its header."""
    out = {}
    for f in files:
        try:
            rel = str(f.resolve().relative_to(repo))
        except ValueError:
            continue
        if f.suffix in SMELL_EXTS and maintained(rel) and f.is_file():
            text = f.read_text(errors="replace")
            if not GENERATED.search("\n".join(text.splitlines()[:5])):
                out[rel] = text
    return out


def base_texts(repo: Path, base: str, rels: List[str]) -> Dict[str, str]:
    """The files as they were at `base`, read by one `git cat-file --batch`; files it lacks are left out."""
    query = "".join(f"{base}:{rel}\n" for rel in rels).encode()
    try:
        out = subprocess.run(["git", "cat-file", "--batch"], input=query, cwd=repo, capture_output=True,
                             timeout=GIT_TIMEOUT).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    texts, pos = {}, 0
    for rel in rels:
        end = out.find(b"\n", pos)
        if end < 0:
            break
        line, pos = out[pos:end], end + 1
        if line.endswith((b" missing", b" ambiguous")):
            continue  # "<name> missing" has no body; the name may hold spaces
        _, kind, size = line.split()  # "<sha> <type> <size>", then the body and a newline
        if kind == b"blob":
            texts[rel] = out[pos:pos + int(size)].decode(errors="replace")
        pos += int(size) + 1
    return texts


def find_smells(repo: Path, files: List[Path], base: Optional[str]) -> Tuple[List[Smell], List[str]]:
    """Smells in `files` that are new or worse than at `base`; every smell when `base` is None."""
    now_text = current_texts(repo, files)
    if not now_text:
        return [], []
    lim, notes = limits(repo), []
    old_text = base_texts(repo, base, list(now_text)) if base else None
    with tempfile.TemporaryDirectory(prefix="broom-smells-") as tmp, ThreadPoolExecutor(2) as pool:
        now = pool.submit(measure, Path(tmp) / "now", now_text, lim, repo, notes)
        before = pool.submit(measure, Path(tmp) / "before", old_text, lim, repo, []) if old_text else None
        off = tuple(repo_config(repo).get("smells_off") or ())
        found = compare(now.result(), before.result() if before else ([] if base else None), lim, repo, off)
    return found, list(dict.fromkeys(notes))


def gate_smells(repo: Path, files: List[Path], known: set, base: str = "HEAD"
                ) -> Tuple[List[Issue], List[Smell], List[str]]:
    """For the hooks: the smells that block (as issues), the hints, and notes. Known ones are left out."""
    if setting("smells", repo) == "off":
        return [], [], []
    found, notes = find_smells(repo, files, base)
    blocks = [s.issue() for s in found if s.level == "block"]
    hints = [s for s in found if s.level == "hint" and issue_key(s.issue()) not in known]
    return [i for i in blocks if issue_key(i) not in known], hints, notes


def hint_text(hints: List[Smell]) -> str:
    shown = "; ".join(f"{s.file.relative_to(s.repo)}:{s.line} {s.text()}" for s in hints[:HINTS_SHOWN])
    more = f"; and {len(hints) - HINTS_SHOWN} more" if len(hints) > HINTS_SHOWN else ""
    return f"broom: {len(hints)} code smell(s) this change made worse; clean them up now: {shown}{more}"
