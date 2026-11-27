"""One code smell as a change finds it, and how it reads: the size or count, what it was at the base, its level, and
the sentence that says so. Where a size stands against a soft and a hard limit is here too, and when that counts as
the change's doing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .clones import Clone
from .config import DEAD_CODE, NIT, NOTED, SMELL_PRESENCE, TEST_LIES
from .findings import Issue

DESCRIBE = {
    "function_lines": "{key} is {value} code lines long",
    "file_lines": "the file is {value} code lines long",
    "params": "{key} takes {value} parameters",
    "nesting": "blocks nest {value} levels deep",
    "complexity": "{key} has complexity {value}",
    "nested_ternary": "a ternary nests inside another",
    "type_lines": "{key} is {value} code lines long",
    "duplicate_lines": "{value} lines repeat {key}",
    DEAD_CODE: "{key} is never used outside tests",  # a test that uses it doesn't count: tests are left out
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
    "globals": "global statement(s) or module variable(s) assigned in a function",
    "bool_params": "boolean flag parameter(s)",
    "broad_test_asserts": "too broad test assertion(s)",
    "broad_catch": "handler(s) that catch every error",
    "missing_docs": "public module(s), class(es) or function(s) with no doc comment",
    "import_cycle": "import(s) that close a cycle between modules",
    "folder_cycle": "import(s) that close a cycle between folders",
    "skipped_test": "skipped or disabled test(s)",
    "untested_file": "new code file(s) with no test file beside it by name",
    "deprecated_api": "call(s) to a deprecated API",
}
# The extreme of a broad assertion is none at all: a test that asserts nothing passes whatever the code does. It is the
# same smell, `broad_test_asserts`, told apart by its key: a row's starts `ASSERTS_NOTHING`, and its finding's is it.
ASSERTS_NOTHING = "asserts nothing"
LABELS[ASSERTS_NOTHING] = "test(s) that assert nothing"


def nothing_key(name: str) -> str:
    """The key of a row of a test that asserts nothing, named `name`: it matches the test across versions."""
    return f"{ASSERTS_NOTHING}: {name}"


def kind_of(metric: str, key: str) -> str:
    """The kind of an occurrence row of `metric` keyed `key`: `ASSERTS_NOTHING` for a test that asserts nothing, else
    the metric. Each kind is a finding of its own, with its own words and level."""
    return ASSERTS_NOTHING if metric == "broad_test_asserts" and key.startswith(ASSERTS_NOTHING) else metric
LINES_SHOWN = 5
NOTE_CHARS = 240  # how much of a finding's own words a NOTED smell's text keeps


@dataclass
class Smell:
    """One smell: its file, line, metric and value, the limit it passed, and whether it is a note, a hint or a block."""
    repo: Path
    file: Path
    line: int
    metric: str
    key: str
    value: int  # the size, or for an occurrence smell the count in the file
    was: Optional[int]
    tool: str
    level: str  # "nit" (told, never stops), "hint" past the soft limit, "block" past the hard one; a hint stops too
    limit: int
    added: List[int] = field(default_factory=list)  # an occurrence smell's lines this change added
    compared: bool = True  # measured against a base; a whole-repo scan isn't, so nothing in it is "new"
    touched: bool = False  # an old smell the change didn't make worse, in a unit it touched
    span: int = 0  # how many lines of the file a function or a type takes from `line` on, where its tool says

    def __post_init__(self) -> None:
        """The one place the level is settled for a test file (decision 051): only `TEST_LIES` keep theirs, every
        other smell there is a nit, whatever its size and whether it is old."""
        from .testrot import TEST_FILE  # testrot builds smells, so it can't be imported above
        try:
            rel = self.file.relative_to(self.repo).as_posix()
        except ValueError:
            return
        if self.metric not in TEST_LIES and TEST_FILE.search(rel):
            self.level = NIT

    def text(self) -> str:
        """The message for this smell: what it is, its limit, and how it compares with the base (new, or was N)."""
        if self.metric == DEAD_CODE:
            return DESCRIBE[DEAD_CODE].format(key=self.key, value=self.value)
        if self.metric in SMELL_PRESENCE:
            where = ", ".join(map(str, self.added[:LINES_SHOWN])) + (" ..." if len(self.added) > LINES_SHOWN else "")
            where += self.note()
            if self.was is None:
                return f"{self.value} {self.label()} at line(s) {where}"
            return (f"{self.value - self.was} more {self.label()} ({self.value} in the file, was {self.was}); "
                    f"new or changed at line(s) {where}")
        what = DESCRIBE[self.metric].format(key=self.key, value=self.value)
        bar = f"hard limit {self.limit}" if self.level == "block" else f"over {self.limit}"
        if not self.compared:
            return f"{what} ({bar})"
        how = "new" if self.was is None else f"was {self.was}"
        if self.touched:
            how += ": you touched it, clean it up in this change"
        return f"{what} ({bar}; {how})"

    def label(self) -> str:
        """What an occurrence smell's finding calls what it counts, by its kind (`kind_of`)."""
        return LABELS[kind_of(self.metric, self.key)]

    def note(self) -> str:
        """What the tool said of a NOTED smell's first finding, in brackets and cut at NOTE_CHARS; else nothing."""
        if self.metric not in NOTED:
            return ""
        return f" ({self.key[:NOTE_CHARS]}{'...' if len(self.key) > NOTE_CHARS else ''})"

    def grew_past_hard(self) -> bool:
        """A sized smell that was already past its hard limit at the base and grew: it can't be accepted with a
        reason, only fixed. One that crossed the hard limit with this change can."""
        return (self.level == "block" and self.metric not in SMELL_PRESENCE and self.was is not None
                and self.was > self.limit and self.value > self.was)

    def issue(self) -> Issue:
        """The smell as a gate finding: severe when it blocks, and marked grown when it grew past the hard limit."""
        return Issue("smells", self.repo, self.file, self.line, 0, self.metric, self.text(),
                     severe=self.level == "block", grown_from=self.was if self.grew_past_hard() else None)


LEVELS = ("", "hint", "block")


def level(value: int, limit: Tuple[int, int]) -> str:
    """The level of `value` against `limit` (soft, hard): "block" past the hard, "hint" past the soft, else ""."""
    soft, hard = limit
    if value > hard:
        return "block"
    return "hint" if value > soft else ""


def made_worse(value: int, old: Optional[int], limit: Tuple[int, int]) -> bool:
    """Pushed past a limit, or grown while past the hard one. Growth below that is noise: a 600-line file that
    gains a line was already over 400, and saying so on every edit teaches Claude to ignore broom."""
    was = level(old, limit) if old is not None else ""
    now = level(value, limit)
    return LEVELS.index(now) > LEVELS.index(was) or (now == "block" and old is not None and value > old)


class Scan(List[Smell]):
    """The smells a scan found, as a list, and with them the clones between two test files that the same scan saw. Those
    are no smells, since the checks on a change leave tests that repeat their setup alone (decision 010); the
    whole-repo diagnosis and the check-up keep them apart."""

    def __init__(self, smells: Iterable[Smell] = (), duplicate_tests: Optional[List[Clone]] = None) -> None:
        super().__init__(smells)
        self.duplicate_tests: List[Clone] = duplicate_tests or []
