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
from typing import Dict, List, Optional, Set, Tuple

from .findings import Issue
from .clones import Clone, Unused, find_clones, find_unused
from .config import DEAD_CODE, LIMIT_PAIR, SMELL_LIMITS, SMELL_PRESENCE, repo_config, setting
from .gate import issue_key
from .gitutil import ChangedLines, renamed
from .maintained import Maintained
from .measure import SMELL_EXTS, Limits, Raw, code_lines, measure

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
    "duplicate_lines": "{value} lines repeat {key}",
    DEAD_CODE: "{key} is never used",
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
    compared: bool = True  # measured against a base; a whole-repo scan isn't, so nothing in it is "new"

    def text(self) -> str:
        if self.metric == DEAD_CODE:
            return DESCRIBE[DEAD_CODE].format(key=self.key, value=self.value)
        if self.metric in SMELL_PRESENCE:
            where = ", ".join(map(str, self.added[:LINES_SHOWN])) + (" ..." if len(self.added) > LINES_SHOWN else "")
            if self.was is None:
                return f"{self.value} {LABELS[self.metric]} at line(s) {where}"
            return (f"{self.value - self.was} more {LABELS[self.metric]} ({self.value} in the file, was {self.was}); "
                    f"new or changed at line(s) {where}")
        what = DESCRIBE[self.metric].format(key=self.key, value=self.value)
        bar = f"hard limit {self.limit}" if self.level == "block" else f"over {self.limit}"
        if not self.compared:
            return f"{what} ({bar})"
        how = "new" if self.was is None else f"was {self.was}"
        return f"{what} ({bar}; {how})"

    def issue(self) -> Issue:
        return Issue("smells", self.repo, self.file, self.line, 0, self.metric, self.text(),
                     severe=self.level == "block")


def moved(base: Limits, pairs: object) -> Limits:
    """`base` with the pairs a .broom.json entry sets: {"function_lines": [50, 100], ...}."""
    out = dict(base)
    for name, pair in (pairs if isinstance(pairs, dict) else {}).items():
        if name in out and isinstance(pair, list) and len(pair) == LIMIT_PAIR and all(isinstance(n, int) for n in pair):
            out[name] = (pair[0], pair[1])
    return out


class RepoLimits:
    """broom's limits as the repo's .broom.json moves them: `limits` for all code, then `test_limits` on top of
    those for test files, which grow long by listing cases rather than by doing more."""

    def __init__(self, repo: Path) -> None:
        config = repo_config(repo)
        self.code = moved(SMELL_LIMITS, config.get("limits"))
        self.test = moved(self.code, config.get("test_limits"))
        # The tools report what is past the soft limit they get: the lower of the two, so neither set misses one.
        self.measured = {k: (min(self.code[k][0], self.test[k][0]), self.code[k][1]) for k in self.code}

    def of(self, rel: str) -> Limits:
        return self.test if TEST_FILE.search(rel) else self.code


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


def compare_sizes(now: List[Raw], before: Optional[List[Raw]], lim: RepoLimits, repo: Path) -> List[Smell]:
    was = {(r.rel, r.metric, r.key): r.value for r in before or []}
    out = []
    for r in now:
        old = was.get((r.rel, r.metric, r.key))
        pair = lim.of(r.rel)[r.metric]
        at = level(r.value, pair)
        if at and (before is None or made_worse(r.value, old, pair)):
            limit = pair[1] if at == "block" else pair[0]
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


def compare(now: List[Raw], before: Optional[List[Raw]], lim: RepoLimits, repo: Path,
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


def current_texts(repo: Path, files: List[Path], keep: Maintained) -> Dict[str, str]:
    """The files' text, leaving out what nobody maintains here: decided by path before any file is read, then
    generated code by its header."""
    out = {}
    for f in files:
        try:
            rel = str(f.resolve().relative_to(repo))
        except ValueError:
            continue
        if f.suffix in SMELL_EXTS and keep.record(rel) and f.is_file():
            text = f.read_text(errors="replace")
            if not GENERATED.search("\n".join(text.splitlines()[:5])):
                out[rel] = text
    return out


def base_texts(repo: Path, base: str, rels: List[str], was: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The files as they were at `base`, read by one `git cat-file --batch`; files it lacks are left out. `was`
    maps a renamed file to its path at `base`."""
    was = was or {}
    query = "".join(f"{base}:{was.get(rel, rel)}\n" for rel in rels).encode()
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


def generated(path: Path) -> bool:
    try:
        with path.open(errors="replace") as f:
            return bool(GENERATED.search("".join(f.readline() for _ in range(5))))
    except OSError:
        return False


def clone_smells(keep: Maintained, clones: List[Clone], scope: set, base: Optional[str],
                 lim: RepoLimits) -> List[Smell]:
    """New duplicate blocks with a side in `scope`, the files measured (every clone when `base` is None), the other
    side code someone maintains. Clones between two test files are left out: tests repeat their setup on purpose.
    So are clones of legacy code, which the new code is there to replace."""
    repo = keep.repo
    out = []
    for c in clones:
        sides = [(c.rel, c.line, c.other, c.other_line), (c.other, c.other_line, c.rel, c.line)]
        mine = next((s for s in sides if s[0] in scope), None)
        if (base is not None and not c.new) or mine is None or not keep(mine[2]) or generated(repo / mine[2]):
            continue
        if keep.legacy(c.rel) or keep.legacy(c.other):
            continue
        pair = lim.of(mine[0])["duplicate_lines"]
        at = level(c.lines, pair)
        if at and not (TEST_FILE.search(c.rel) and TEST_FILE.search(c.other)):
            limit = pair[1] if at == "block" else pair[0]
            out.append(Smell(repo, repo / mine[0], mine[1], "duplicate_lines", f"{mine[2]}:{mine[3]}", c.lines,
                             None, "jscpd", at, limit))
    return out


def unused_smells(repo: Path, unused: List[Unused], scope: set, base: Optional[str]) -> List[Smell]:
    """Dead code in `scope` on lines the change added, a new file included (every finding when `base` is None):
    something Claude wrote and never wired in. A hint only: what loads dynamically (a manifest's scripts, plugins)
    looks unused too."""
    changed = ChangedLines(base) if base else None
    out = []
    for u in unused:
        lines = changed.get(repo / u.rel) if changed else None
        if u.rel in scope and (lines is None or u.line in lines):
            out.append(Smell(repo, repo / u.rel, u.line, DEAD_CODE, u.what, 1, None, "jscpd", "hint", 0))
    return out


def drop_import_growth(rows: List[Raw], now: Dict[str, str], before: Optional[Dict[str, str]]) -> List[Raw]:
    """`rows` without the file length of files whose lines besides imports didn't grow since `before`: rewired
    imports (a moved module's new paths, a formatter's line breaks) don't make a long file worse."""
    steady: Set[str] = {rel for rel, text in now.items()
                        if before and rel in before and code_lines(rel, text) <= code_lines(rel, before[rel])}
    return [r for r in rows if not (r.metric == "file_lines" and r.rel in steady)]


def find_smells(repo: Path, files: List[Path], base: Optional[str]) -> Tuple[List[Smell], List[str]]:
    """Smells in `files` that are new or worse than at `base`; every smell when `base` is None. A file renamed
    since `base` is compared with its old path."""
    keep = Maintained(repo)
    now_text = current_texts(repo, files, keep)
    notes = [n for n in (keep.note(),) if n]
    if not now_text:
        return [], notes
    lim = RepoLimits(repo)
    off = tuple(repo_config(repo).get("smells_off") or ())
    old_text = base_texts(repo, base, list(now_text), renamed(repo, [base])) if base else None
    with tempfile.TemporaryDirectory(prefix="broom-smells-") as tmp, ThreadPoolExecutor(4) as pool:
        now = pool.submit(measure, Path(tmp) / "now", now_text, lim.measured, repo, notes)
        before = pool.submit(measure, Path(tmp) / "before", old_text, lim.measured, repo, []) if old_text else None
        clones = None if "duplicate_lines" in off else pool.submit(
            find_clones, repo, base, lim.measured["duplicate_lines"][0] + 1, keep.clone_skips(), notes)
        unused = None if DEAD_CODE in off else pool.submit(find_unused, repo, keep.dead_code_skips(), notes)
        found = compare(drop_import_growth(now.result(), now_text, old_text),
                        before.result() if before else ([] if base else None), lim, repo, off)
        found += clone_smells(keep, clones.result() if clones else [], set(now_text), base, lim)
        found += unused_smells(repo, unused.result() if unused else [], set(now_text), base)
    for s in found:
        s.compared = base is not None
    return sorted(found, key=lambda s: (s.level != "block", str(s.file), s.line)), list(dict.fromkeys(notes))


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
