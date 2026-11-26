"""No rule turns on the clock (goal R7, design 10): what broom holds back waits for an event, and what it trims goes by
size or count. Every reading of the clock in lib/broom is listed here with what it is for, and none of them decides by
how much time passed: one bounds broom's own running time, stamps a record, orders two events, or tells that a file
changed. A new one fails until it is listed."""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

LIB = Path(__file__).resolve().parent.parent / "lib" / "broom"
TIME_CALLS = {"time", "monotonic", "strftime", "localtime", "gmtime", "perf_counter"}
FILE_TIMES = {"st_mtime", "st_mtime_ns", "st_ctime", "st_ctime_ns", "st_atime", "st_atime_ns"}
GIT_TIMES = ("%ct", "%at", "%cd", "%ad", "%cr", "%ar", "--since", "--until", "--before", "--after")

RUNTIME = "bounds or measures broom's own running time"
STAMP = "stamps a record, which is shown or only orders records"
ORDER = "orders two events"
CHANGE = "tells that a file changed"

# (module, the function around it, or "" at module level) -> what the clock is read for, and one short reason.
ALLOWED: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("asks", "add_ask_parsers"): (ORDER, "report's --since takes a broom version, not a day"),
    ("asks", "broom_version"): (ORDER, "report's --since takes a broom version, not a day"),
    ("asks", "cmd_report"): (ORDER, "report's --since takes a broom version, not a day"),
    ("checks", "timed"): (RUNTIME, "how long a check ran, to tell one that timed out"),
    ("checkup", "check_up.keep"): (STAMP, "the day of the last check-up, as it is shown"),
    ("cli", "cmd_known"): (STAMP, "the day an issue was accepted, as broom known shows it"),
    ("commitgate", "checked"): (RUNTIME, "a whole check's seconds, for the record"),
    ("compare", "compare"): (RUNTIME, "how long a compare took, as it is shown"),
    ("coverage", "behind"): (ORDER, "a covered file written after the report"),
    ("coverage", "report_path"): (ORDER, "the coverage report written last"),
    ("coverage", "section"): (ORDER, "when the report was written, for behind"),
    ("diagnose", "diagnose"): (RUNTIME, "how long a diagnosis took, as it is shown"),
    ("doctor", "cache_key"): (CHANGE, "a tool's file changed, so its answer is read again"),
    ("gate", "accept_blocked"): (STAMP, "when an issue was accepted"),
    ("gate", "issue_entry"): (STAMP, "when an issue was recorded"),
    ("gitutil", "Clock.left"): (RUNTIME, "the time a hook run has left"),
    ("gitutil", "Clock.start"): (RUNTIME, "the time a hook run has left"),
    ("hookmain", "give_up_after"): (RUNTIME, "the last resort before Claude Code ends the hook"),
    ("hooktrace", "watch"): (RUNTIME, "a hook still running is traced"),
    ("hooktrace", "write"): (RUNTIME, "a hook still running is traced"),
    ("langlint", "check_swift_build"): (RUNTIME, "the time swift build may take"),
    ("ledger", "line"): (STAMP, "when a line was written"),
    ("passed", "record"): (STAMP, "orders records, so the oldest go first past the count"),
    ("realtree", "Budget.__init__"): (RUNTIME, "the time the tools of the real tree share"),
    ("realtree", "Budget.timeout"): (RUNTIME, "the time the tools of the real tree share"),
    ("rowcache", "RowCache.measure"): (STAMP, "orders entries, so the oldest go first past the count"),
    ("standing", "accept_standing"): (STAMP, "when a smell was accepted"),
    ("state", "locked"): (RUNTIME, "how long a lock is waited for"),
    ("state", "newest_first"): (ORDER, "the folders touched last are kept"),
    ("state", "read_hook_input"): (RUNTIME, "how long a hook waits for its input"),
    ("testrot", "newer_side.written"): (ORDER, "the side of a copy written last"),
    ("testrun", "note_run"): (STAMP, "when a test run was noted"),
    ("turns", "committed_in_turn"): (ORDER, "a commit made after the prompt (decision 041)"),
    ("turns", "snapshot"): (ORDER, "when the prompt came, for decision 041"),
    ("turns", "tree"): (CHANGE, "a file changed since the prompt"),
    ("turns", "turn_base"): (ORDER, "the commits made after the prompt (decision 041)"),
}


def readings(path: Path) -> Iterator[Tuple[str, int]]:
    """(function, line) of each reading of the clock in the module at `path`: a call of `time`'s clock functions, a
    file's time, `datetime`, a `threading.Timer`, or git's time formats and windows in a string."""
    tree = ast.parse(path.read_text())
    todo: List[Tuple[ast.AST, str]] = [(tree, "")]
    while todo:
        node, where = todo.pop()
        for child in ast.iter_child_nodes(node):
            inner = where
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = f"{where}.{child.name}" if where else child.name
            if clock(child):
                yield inner, child.lineno
            todo.append((child, inner))


def clock(node: ast.AST) -> bool:
    """Whether `node` reads the clock."""
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "time" and node.attr in TIME_CALLS:
            return True
        if isinstance(node.value, ast.Name) and node.value.id == "threading" and node.attr == "Timer":
            return True
        return node.attr in FILE_TIMES
    if isinstance(node, ast.Name):
        return node.id == "datetime"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return any(word in node.value for word in GIT_TIMES)
    return False


class NoClockTest(unittest.TestCase):
    def test_every_reading_of_the_clock_is_listed_and_decides_nothing_by_time(self) -> None:
        seen = set()
        unknown = []
        for path in sorted(LIB.glob("*.py")):
            for where, line in readings(path):
                seen.add((path.stem, where))
                if (path.stem, where) not in ALLOWED:
                    unknown.append(f"{path.stem}.py:{line} ({where})")
        self.assertEqual(unknown, [], "no rule may turn on the clock: wait for an event and trim by size or count "
                         "(decision 048); a reading that only bounds broom's running time, stamps a record, orders two "
                         "events or tells that a file changed goes in ALLOWED with its reason")
        self.assertEqual(sorted(set(ALLOWED) - seen), [], "an entry in ALLOWED no longer reads the clock: remove it")

    def test_a_new_reading_is_found_wherever_it_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mod = Path(tmp) / "m.py"
            mod.write_text("import time\nT = time.time()\nclass C:\n    def f(self, p):\n        return p.stat().st_mtime\n"
                           "def g(git):\n    return git(['log', '--since=90.days'])\n")
            self.assertEqual(sorted(readings(mod)), [("", 2), ("C.f", 5), ("g", 7)])

    def test_each_entry_says_what_the_clock_is_for(self) -> None:
        for key, (kind, reason) in ALLOWED.items():
            self.assertIn(kind, {RUNTIME, STAMP, ORDER, CHANGE}, key)
            self.assertTrue(reason and len(reason) <= 80, key)


if __name__ == "__main__":
    unittest.main()
