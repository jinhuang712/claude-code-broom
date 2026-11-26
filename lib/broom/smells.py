"""Code smells, of two kinds. Sized ones (long functions, files and types, many parameters, deep nesting, high
complexity) have a soft and a hard limit; the rest count by occurrence (suppressions without a reason,
swallowed errors, commented-out code, magic numbers, TODOs, type escapes, and so on) at a fixed level.

They are measured against broom's own limits, apart from the project's lint config, so one bar holds in every
repo; `.broom.json` can move it. Only what a change made worse counts: each file is measured as it is and as it
was at the base revision. A sized smell counts when the change pushed it past a limit, or grew it while past
the hard one; an occurrence counts when the change added it. Legacy code a change leaves as it was never comes
up, except that an old sized smell in a function or file the change touches is a hint (see touched).
"""

from __future__ import annotations

import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .findings import Issue
from .fixes import fix_lines
from .change import Change
from .clones import Clone, Unused, find_clones, find_unused
from .codelines import CodeLines, code_lines
from .config import (
    DEAD_CODE, LIMIT_PAIR, NIT, NOTED, SMELL_LIMITS, SMELL_PRESENCE, TEST_FILE_FACTOR, repo_config, setting,
)
from .gate import issue_key
from .gitutil import ChangedLines, renamed, run_bytes
from .maintained import Maintained, generated, generated_among
from .imports import import_lines
from .measure import SMELL_EXTS, Limits, Raw
from .realtree import Budget, Found, find_in_real_tree
from .rowcache import RowCache
from .smell import Scan, Smell, level, made_worse
from .testrot import TEST_FILE, UNTESTED_FILE, skip_rows, test_clones, untested_smells
from .touched import old_smells, touched, touches
from .toolchain import GO_EXTS, JS_EXTS, RS_EXTS, SWIFT_EXTS

GIT_TIMEOUT = 60

NITS_SHOWN = 10
NIT_KINDS = 3  # how many kinds of smell a nit message gives the fix of


def moved(base: Limits, pairs: object) -> Limits:
    """`base` with the pairs a .broom.json entry sets: {"function_lines": [50, 100], ...}."""
    out = dict(base)
    for name, pair in (pairs if isinstance(pairs, dict) else {}).items():
        if name in out and isinstance(pair, list) and len(pair) == LIMIT_PAIR and all(isinstance(n, int) for n in pair):
            out[name] = (pair[0], pair[1])
    return out


def for_tests(code: Limits) -> Limits:
    """The limits a test file starts from: the code's `code`, with a file `TEST_FILE_FACTOR` times as long."""
    soft, hard = code["file_lines"]
    return {**code, "file_lines": (soft * TEST_FILE_FACTOR, hard * TEST_FILE_FACTOR)}


class RepoLimits:
    """broom's limits as the repo's .broom.json moves them: `limits` for all code, then for test files a file twice
    as long and `test_limits` on top, since tests grow long by listing cases rather than by doing more."""

    def __init__(self, repo: Path) -> None:
        config = repo_config(repo)
        self.code = moved(SMELL_LIMITS, config.get("limits"))
        self.test = moved(for_tests(self.code), config.get("test_limits"))
        # The tools report what is past the soft limit they get: the lower of the two, so neither set misses one.
        self.measured = {k: (min(self.code[k][0], self.test[k][0]), self.code[k][1]) for k in self.code}

    def of(self, rel: str) -> Limits:
        """The limits that apply to file `rel`: the test limits for a test file, else the code limits."""
        return self.test if TEST_FILE.search(rel) else self.code


# ---------------------------------------------------------------- comparing versions


# What a test file doesn't owe: complexity counts every assertion's `if`, magic numbers are the fixtures, and a test
# or a helper beside it needs no doc comment.
TEST_NOISE = ("complexity", "magic_numbers", "missing_docs")


def noise(r: Raw) -> bool:
    """Findings that measure the tool, not the code: in tests, what `TEST_NOISE` names. A test framework's
    describe/it callbacks, long by nature, are left out where they are measured (jsmeasure.drop_test_callbacks)."""
    return r.metric in TEST_NOISE and bool(TEST_FILE.search(r.rel))


def compare_sizes(now: List[Raw], before: Optional[List[Raw]], lim: RepoLimits, repo: Path) -> List[Smell]:
    """Smells for the sized rows `now` past their limit and new or worse than in `before`; None means a first run."""
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


# Where a smell is found by a guess, not a parse, it is only a nit even when the same smell blocks in another
# language. In Rust `let _ = f();` drops a Result by design as often as by mistake, and clippy can't tell which.
GUESSED = {"commented_code": JS_EXTS | GO_EXTS | RS_EXTS | SWIFT_EXTS, "swallowed_error": RS_EXTS}
# The same by the tool that finds it, where the language's other finder of that smell is sure: Go's `_ = f()`, which
# golangci-lint's errcheck finds, drops an error by design as often (`_ = conn.Close()`); an empty block doesn't.
GUESSED_BY = {("swallowed_error", "golangci-lint")}


def presence_level(metric: str, rel: str, tool: str = "") -> str:
    """The level of a presence smell in file `rel` found by `tool`: a nit for a kind guessed, by text or by a tool
    that can't tell a deliberate one, else its normal level."""
    guessed = Path(rel).suffix in GUESSED.get(metric, ()) or (metric, tool) in GUESSED_BY
    return NIT if guessed else SMELL_PRESENCE[metric]


def example(metric: str, rows: list) -> str:
    """The key of an occurrence smell: its metric, or for a NOTED smell what its first finding says."""
    return rows[0].key if metric in NOTED else metric


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
    return [Smell(repo, repo / rel, rows[0].line, metric, example(metric, rows), total[(rel, metric)],
                  None if before is None else was[(rel, metric)], rows[0].tool, presence_level(metric, rel, rows[0].tool), 0,
                  [r.line for r in rows])
            for (rel, metric), rows in added.items() if before is None or total[(rel, metric)] > was[(rel, metric)]]


def counted(now: List[Raw], off: Tuple[str, ...]) -> List[Raw]:
    """The rows that count: of a smell the repo hasn't turned off, and not the tool's noise."""
    return [r for r in now if r.metric not in off and not noise(r)]


def compare(now: List[Raw], before: Optional[List[Raw]], lim: RepoLimits, repo: Path,
            off: Tuple[str, ...] = ()) -> List[Smell]:
    """`before` is None to report every finding (a whole-repo sweep), else the base version's findings. `off`
    names smells the repo turned off."""
    kept = counted(now, off)
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
            out[rel] = f.read_text(errors="replace")
    made = generated_among(repo, out)
    return {rel: text for rel, text in out.items() if rel not in made}


def base_texts(repo: Path, base: str, rels: List[str], was: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The files as they were at `base`, read by one `git cat-file --batch`; files it lacks are left out. `was`
    maps a renamed file to its path at `base`."""
    was = was or {}
    query = "".join(f"{base}:{was.get(rel, rel)}\n" for rel in rels).encode()
    rc, out, _ = run_bytes(["git", "cat-file", "--batch"], repo, timeout=GIT_TIMEOUT, stdin=query)
    if rc is None or rc < 0:
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


def clone_smells(keep: Maintained, clones: List[Clone], scope: set, base: Optional[str],
                 lim: RepoLimits) -> List[Smell]:
    """New duplicate blocks with a side in `scope`, the files measured (every clone when `base` is None), the other
    side code someone maintains. Clones between two test files are left out: tests repeat their setup on purpose.
    So are clones of legacy code, which the new code is there to replace. A block's size is the code lines of the span
    on the side measured (decision 039), so a clone of comments and blanks falls short of the limit."""
    repo = keep.repo
    out = []
    for c in clones:
        sides = [(c.rel, c.line, c.other, c.other_line, c.lines), (c.other, c.other_line, c.rel, c.line, c.other_lines)]
        mine = next((s for s in sides if s[0] in scope), None)
        if (base is not None and not c.new) or mine is None or not keep(mine[2]) or generated(repo / mine[2]):
            continue
        if keep.legacy(c.rel) or keep.legacy(c.other):
            continue
        pair = lim.of(mine[0])["duplicate_lines"]
        at = level(mine[4], pair)
        if at and not (TEST_FILE.search(c.rel) and TEST_FILE.search(c.other)):
            limit = pair[1] if at == "block" else pair[0]
            out.append(Smell(repo, repo / mine[0], mine[1], "duplicate_lines", f"{mine[2]}:{mine[3]}", mine[4],
                             None, "jscpd", at, limit))
    return out


def unused_smells(repo: Path, unused: List[Unused], scope: set, base: Optional[str]) -> List[Smell]:
    """Dead code in `scope` on lines the change added, a new file included (every finding when `base` is None):
    something Claude wrote and never wired in. A note only: what loads dynamically (a manifest's scripts, plugins)
    looks unused too."""
    changed = ChangedLines(base) if base else None
    out = []
    for u in unused:
        lines = changed.get(repo / u.rel) if changed else None
        if u.rel in scope and (lines is None or u.line in lines):
            out.append(Smell(repo, repo / u.rel, u.line, DEAD_CODE, u.what, 1, None, "jscpd", NIT, 0))
    return out


def touched_function(repo: Path, f: Found, lines: Set[int], lim: RepoLimits) -> List[Smell]:
    """A long function in the real tree whose first line the change didn't add, as the touched hint when a changed
    line lies in it (the length is what its row says, which only a function's length does). No copy of the base says
    what it was, so the size now stands in for it."""
    pair = lim.of(f.rel).get(f.metric) if f.metric == "function_lines" else None
    if not pair or not level(f.value, pair):
        return []
    s = Smell(repo, repo / f.rel, f.line, f.metric, f.key, f.value, f.value, f.tool, "hint", pair[0], touched=True,
              span=f.span)
    return [s] if touches(s, lines, "") else []


def real_tree_smells(found: List[Found], change: Change, lim: RepoLimits, off: Tuple[str, ...]) -> List[Smell]:
    """What the tools run in the real tree found on lines the change added, a new file included (all of it when
    there is no base): without a copy of the base, that is what makes a smell the change's own. A long function the
    change only edited the inside of is the old smell of a function it touched. An occurrence on a line the change
    only moved is an old one."""
    repo = change.repo
    added: Dict[Tuple[str, str], List[Found]] = {}
    out = []
    for f in found:
        lines = change.lines(f.rel)
        if f.metric in off:
            continue
        if not (lines is None or f.line in lines):
            out += touched_function(repo, f, change.code_lines(f.rel) or set(), lim)
            continue
        if f.metric in SMELL_PRESENCE and change.only_moved(f.rel, f.line):
            continue
        if f.metric in SMELL_PRESENCE:
            added.setdefault((f.rel, f.metric), []).append(f)
        elif f.metric == DEAD_CODE:
            out.append(Smell(repo, repo / f.rel, f.line, DEAD_CODE, f.key, 1, None, f.tool, NIT, 0))
        else:
            pair = lim.of(f.rel)[f.metric]
            at = level(f.value, pair)
            if at:
                out.append(Smell(repo, repo / f.rel, f.line, f.metric, f.key, f.value, None, f.tool, at,
                                 pair[1] if at == "block" else pair[0]))
    for (rel, metric), rows in added.items():
        out.append(Smell(repo, repo / rel, rows[0].line, metric, example(metric, rows), len(rows), None, rows[0].tool,
                         presence_level(metric, rel, rows[0].tool), 0, [r.line for r in rows]))
    return out


def drop_import_growth(rows: List[Raw], now: Dict[str, str], before: Optional[Dict[str, str]],
                       notes: List[str]) -> List[Raw]:
    """`rows` without the file length of files whose code lines besides imports didn't grow since `before`: rewired
    imports (a moved module's new paths, a formatter's line breaks) don't make a long file worse, and comments and
    blank lines are no code lines at all. The imports and the code lines are read from each version's tree."""
    was = before or {}
    long = sorted({r.rel for r in rows if r.metric == "file_lines" and r.rel in was and r.rel in now})
    if not long:
        return rows
    texts = {**{f"now/{rel}": now[rel] for rel in long}, **{f"was/{rel}": was[rel] for rel in long}}
    imports = import_lines(texts, notes)
    code = {key: len(lines - imports[key]) for key, lines in code_lines(texts, notes).items()}
    steady = {rel for rel in long if code[f"now/{rel}"] <= code[f"was/{rel}"]}
    return [r for r in rows if not (r.metric == "file_lines" and r.rel in steady)]


def with_skips(rows: Optional[List[Raw]], texts: Optional[Dict[str, str]], notes: List[str]) -> Optional[List[Raw]]:
    """`rows` and the skipped tests of the files in `texts`; None stays None, as a sweep of the whole repo has no base
    to set the rows against."""
    return None if rows is None else rows + skip_rows(texts or {}, notes)


def find_smells(repo: Path, files: List[Path], base: Optional[str],
                budget: Optional[float] = None) -> Tuple[Scan, List[str]]:
    """Smells in `files` that are new or worse than at `base`; every smell when `base` is None. A file renamed
    since `base` is compared with its old path. `budget` is the seconds the tools that run in the real tree have
    between them (no limit when None)."""
    keep = Maintained(repo)
    now_text = current_texts(repo, files, keep)
    notes = [n for n in (keep.note(),) if n]
    if not now_text:
        return Scan(), notes
    lim = RepoLimits(repo)
    off = tuple(repo_config(repo).get("smells_off") or ())
    old_text = base_texts(repo, base, list(now_text), renamed(repo, [base])) if base else None
    rows = RowCache(repo, lim.measured)
    with tempfile.TemporaryDirectory(prefix="broom-smells-") as tmp, ThreadPoolExecutor(5) as pool:
        soft = {metric: pair[0] for metric, pair in lim.measured.items()}
        real = pool.submit(find_in_real_tree, repo, list(now_text), soft, notes, Budget(budget))
        now = pool.submit(rows.measure, Path(tmp) / "now", now_text, notes)
        before = pool.submit(rows.measure, Path(tmp) / "before", old_text, []) if old_text else None
        clones = None if "duplicate_lines" in off else pool.submit(
            find_clones, repo, base, lim.measured["duplicate_lines"][0] + 1, keep.clone_skips(), notes)
        unused = None if DEAD_CODE in off else pool.submit(find_unused, repo, keep.dead_code_skips(), notes)
        unmeasured = [] if base else None  # a base with no file at it makes every row new; no base, a sweep
        old_rows = with_skips(before.result() if before else unmeasured, old_text, notes)
        rows_now = drop_import_growth(now.result(), now_text, old_text, notes) + skip_rows(now_text, notes)
        found = compare(rows_now, old_rows, lim, repo, off)
        code = CodeLines(now_text, notes)
        if base:  # the old smells in what the change touches
            found += touched(old_smells(counted(rows_now, off), old_rows, lim.of, repo), base, now_text, code)
        cloned = clones.result() if clones else []
        found += clone_smells(keep, cloned, set(now_text), base, lim)
        found += unused_smells(repo, unused.result() if unused else [], set(now_text), base)
        found += real_tree_smells(real.result(), Change(repo, base, now_text, old_text, code), lim, off)
        found += [] if UNTESTED_FILE in off else untested_smells(repo, now_text, old_text)
    rows.save()
    for s in found:
        s.compared = base is not None
    ordered = sorted(found, key=lambda s: (s.level != "block", str(s.file), s.line))
    return Scan(ordered, test_clones(keep, cloned, set(now_text), lim.of)), list(dict.fromkeys(notes))


def gate_smells(repo: Path, files: List[Path], known: set, base: str = "HEAD"
                ) -> Tuple[List[Issue], List[Smell], List[str], int]:
    """For the hooks: the smells that stop (as issues: the blocks and the hints), the notes, tool notes, and how many
    known ones were collapsed: left out of the first two, and still counted."""
    if setting("smells", repo) == "off":
        return [], [], [], 0
    found, notes = find_smells(repo, files, base)
    every = [s.issue() for s in found if s.level != NIT]
    told = [s for s in found if s.level == NIT and issue_key(s.issue()) not in known]
    # A smell that grew past the hard limit stays a block whatever was accepted: accepting it is refused.
    stops = [i for i in every if i.grown_from is not None or issue_key(i) not in known]
    nits = sum(s.level == NIT for s in found)
    return stops, told, notes, len(every) - len(stops) + nits - len(told)


def nits_text(told: List[Smell]) -> str:
    """What Claude is told of the nits a change made: the first NITS_SHOWN of them, and to end with, the fix lines
    of the kinds of smell those are, at most NIT_KINDS. Nothing stops on a nit."""
    shown = "; ".join(f"{s.file.relative_to(s.repo)}:{s.line} {s.text()}" for s in told[:NITS_SHOWN])
    more = f"; and {len(told) - NITS_SHOWN} more" if len(told) > NITS_SHOWN else ""
    kinds = list(dict.fromkeys(s.metric for s in told[:NITS_SHOWN]))[:NIT_KINDS]
    fix = fix_lines(kinds)
    return (f"broom: {len(told)} nit(s) this change made worse; nothing stops on them: {shown}{more}"
            + ("\nHow to fix:\n" + "\n".join(fix) if fix else ""))
