"""One code smell as a change finds it, and how it reads: the size or count, what it was at the base, its level, and
the sentence that says so. Where a size stands against a soft and a hard limit is here too, and when that counts as
the change's doing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .config import DEAD_CODE, SMELL_PRESENCE
from .findings import Issue

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
    "globals": "global statement(s) or module variable(s) assigned in a function",
    "bool_params": "boolean flag parameter(s)",
    "broad_test_asserts": "too broad test assertion(s)",
    "import_cycle": "import(s) that close a cycle between modules",
    "folder_cycle": "import(s) that close a cycle between folders",
}
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
    touched: bool = False  # an old smell the change didn't make worse, in a unit it touched

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
        if self.touched:
            how += ": you touched it, clean it up in this change"
        return f"{what} ({bar}; {how})"

    def grew_past_hard(self) -> bool:
        """A sized smell that was already past its hard limit at the base and grew: it can't be accepted with a
        reason, only fixed. One that crossed the hard limit with this change can."""
        return (self.level == "block" and self.metric not in SMELL_PRESENCE and self.was is not None
                and self.was > self.limit and self.value > self.was)

    def issue(self) -> Issue:
        return Issue("smells", self.repo, self.file, self.line, 0, self.metric, self.text(),
                     severe=self.level == "block", grown_from=self.was if self.grew_past_hard() else None)


LEVELS = ("", "hint", "block")


def level(value: int, limit: Tuple[int, int]) -> str:
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
