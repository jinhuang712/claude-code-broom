"""What a repo's tests lose that no linter sees: a test marked skipped, a code file added with no test file beside it
by name, and tests that repeat one another. Each is read from the text of test files, from file names or from the
clones the smell scan already found, so none needs a tool installed.

A test file is told by its path (`TEST_FILE`). A skip counts for the smell when no condition decides it: `skipIf`,
`skipUnless` and the like say when a test runs, which is how a suite fits the machine it is on (a tool that is missing),
not a test that was switched off. `broom stats` and the check-up still count those, as a pile of them is worth seeing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Pattern, Set, Tuple

from .clones import Clone
from .config import SMELL_PRESENCE
from .gitutil import git
from .maintained import Maintained, generated
from .reading import Limits, Raw
from .smell import Smell, level
from .toolchain import lang_of

TEST_FILE = re.compile(r"(^|/)(tests?|__tests__|Tests)/|_test\.(go|py)$|(^|/)test_[^/]*\.py$|"
                       r"\.(test|spec)\.[cm]?[jt]sx?$|Tests?\.swift$")
# How a test is skipped or disabled, per language. Go, Python, JS/TS and Swift are read in test files only (`.skip(` and
# `.disabled` mean other things elsewhere); Rust keeps its tests next to the code.
SKIPS: Dict[str, Pattern[str]] = {lang: re.compile(pattern, re.M) for lang, pattern in {
    "py": r"^[ \t]*@(?:[\w.]+\.)?(?:skip|skipIf|skipUnless|skipif|xfail)\b|\bself\.skipTest\(|\bpytest\.skip\(",
    "js": r"(?<![\w.$])(?:it|test|describe|context|suite)\.skip[ \t]*\(|(?<![\w.$])x(?:it|describe|test)[ \t]*\(",
    "go": r"\b[tb]\.Skip(?:f|Now)?[ \t]*\(",
    "rust": r"#\[ignore\b",
    "swift": r"\bXCTSkip\w*[ \t]*\(|\.disabled\b",
}.items()}
SKIPPED_TEST = "skipped_test"
# A skip named for its condition; or one that sits behind an `if` on its own line or the line above: a guard.
CONDITIONED = re.compile(r"skip(?:If|Unless|if)\b|XCTSkip(?:If|Unless)\b")
GUARD = re.compile(r"\b(?:if|guard|unless)\b")
GUARDED = re.compile(r"^(?:\}\s*)?(?:if|elif|else|except|catch|guard|case)\b")


def is_conditional(row: str, found: re.Match[str], before: str) -> bool:
    """Whether the skip `found` on `row` depends on a condition: its name says so, an `if` stands before it on the row,
    or `before`, the line above, opens a branch."""
    return bool(CONDITIONED.search(found.group()) or GUARD.search(row[:found.start()]) or GUARDED.match(before))


def skip_rows(texts: Dict[str, str]) -> List[Raw]:
    """A row for each skipped or disabled test that no condition decides, in the test files among `texts` (path to
    text; Rust files all count). The key is the line's text, which matches a skip across versions of the file."""
    out = []
    for rel, text in texts.items():
        pattern = SKIPS.get(lang_of(Path(rel)) or "")
        if not pattern or not (TEST_FILE.search(rel) or rel.endswith(".rs")) or not pattern.search(text):
            continue
        before = ""  # the last line with something on it
        for n, row in enumerate(text.splitlines(), 1):
            found = pattern.search(row)
            if found and not is_conditional(row, found, before):
                out.append(Raw(rel, n, SKIPPED_TEST, row.strip(), 1, "broom"))
            before = row.strip() or before
    return out


# ---------------------------------------------------------------- code with no test beside it

# How a test file is named after the code it tests, per language; the pattern matches the file name without its
# extension and holds the code's name in its groups.
PAIRING = {"py": re.compile(r"test_(.+)|(.+)_test"), "go": re.compile(r"(.+)_test"),
           "js": re.compile(r"(.+)\.(?:test|spec)"), "swift": re.compile(r"(.+?)Tests?")}
NO_TEST_NEEDED = {"__init__.py", "conftest.py"}
MIN_CODE_LINES = 30  # a smaller file is a glue file, and a test for it would say less than the code
UNTESTED_FILE = "untested_file"


def stem_of(rel: str) -> str:
    """A file's name without its folder and its extension."""
    return rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def subject_of(rel: str, lang: str) -> Optional[str]:
    """The name of the code a test file is named for (`test_foo.py` and `foo_test.py`, `foo_test.go`, `foo.test.ts` and
    `foo.spec.ts`, `FooTests.swift` are for `foo` or `Foo`), or None when its name follows no such form."""
    pattern = PAIRING.get(lang)
    m = pattern.fullmatch(stem_of(rel)) if pattern else None
    return next((g for g in m.groups() if g), None) if m else None


def tested(files: Iterable[Tuple[str, Optional[str]]]) -> Set[Tuple[str, Optional[str]]]:
    """The (language, name) of the code that each test file among `files` (path, language pairs) is named for."""
    return {(lang, subject_of(rel, lang)) for rel, lang in files if lang and TEST_FILE.search(rel)}


def needs_test(rel: str, lang: Optional[str]) -> bool:
    """Whether the file takes part in the pairing: code of a language with a naming form, and not a test or a file
    that holds nothing to test (`__init__.py`, `conftest.py`)."""
    return lang in PAIRING and not TEST_FILE.search(rel) and rel.rsplit("/", 1)[-1] not in NO_TEST_NEEDED


def non_blank(text: str) -> int:
    """How many lines of `text` have something on them."""
    return sum(1 for row in text.splitlines() if row.strip())


def untested_smells(repo: Path, now: Dict[str, str], old: Optional[Dict[str, str]]) -> List[Smell]:
    """A hint for each code file among `now` (path to text) that `old`, the same files at the base, lacks, that holds at
    least `MIN_CODE_LINES` non-blank lines and has no test file named for it anywhere in the repo, as the pairing goes.
    Without a base (`old` is None) a sweep of the whole repo is no change adding a file, so it finds none."""
    if old is None:
        return []
    added = [rel for rel, text in now.items()
             if rel not in old and needs_test(rel, lang_of(Path(rel))) and non_blank(text) >= MIN_CODE_LINES]
    if not added:
        return []
    listed = (git(["ls-files", "--cached", "--others", "--exclude-standard"], repo) or "").splitlines()
    named = tested((rel, lang_of(Path(rel))) for rel in listed)
    return [Smell(repo, repo / rel, 1, UNTESTED_FILE, UNTESTED_FILE, 1, None, "broom", SMELL_PRESENCE[UNTESTED_FILE],
                  0, [1])
            for rel in added if (lang_of(Path(rel)), stem_of(rel)) not in named]


# ---------------------------------------------------------------- tests that repeat one another

DUPLICATE_TESTS = "duplicate_tests"


def test_clones(keep: Maintained, clones: List[Clone], scope: Set[str],
                limits_of: Callable[[str], Limits]) -> List[Clone]:
    """The clones with both sides in test files that someone maintains here (not generated, not legacy), a side in
    `scope`, and past the duplicate limit of tests: the largest first. The checks on a change leave these out."""
    out = []
    for c in clones:
        sides = (c.rel, c.other)
        if not all(TEST_FILE.search(rel) and keep(rel) and not keep.legacy(rel) for rel in sides):
            continue
        if scope.isdisjoint(sides) or any(generated(keep.repo / rel) for rel in sides):
            continue
        if level(c.lines, limits_of(c.rel)["duplicate_lines"]):
            out.append(c)
    return sorted(out, key=lambda c: (-c.lines, c.rel, c.line))


def newer_side(repo: Path, c: Clone) -> str:
    """The side of a clone that was written last, where the copy is likelier to be: the later path breaks a tie."""

    def written(rel: str) -> int:
        try:
            return (repo / rel).stat().st_mtime_ns
        except OSError:
            return 0

    return max((c.rel, c.other), key=lambda rel: (written(rel), rel))


def duplicate_counter(repo: Path, found: object, notes: List[str], off: Iterable[str]) -> Optional[Dict[str, int]]:
    """The check-up's count of duplicate test blocks per file, each block on its newer side, from the scan `found`. None
    when the scan can't say: no clones in it, the repo turned duplicates off, or jscpd was missing, failed or cut short,
    as a count that low would read as a fall."""
    clones = getattr(found, "duplicate_tests", None)
    if clones is None or {"duplicate_lines", DUPLICATE_TESTS} & set(off) or any("jscpd" in n for n in notes):
        return None
    counts: Dict[str, int] = {}
    for c in clones:
        rel = newer_side(repo, c)
        counts[rel] = counts.get(rel, 0) + 1
    return counts


def duplicate_rows(clones: List[Clone]) -> List[dict]:
    """The clones as the diagnosis shows them, largest first: both places and the lines they share."""
    return [{"file": c.rel, "line": c.line, "other": c.other, "other_line": c.other_line, "lines": c.lines}
            for c in clones]
