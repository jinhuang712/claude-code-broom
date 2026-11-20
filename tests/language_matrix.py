"""The language matrix: every code smell broom has, shown on Python, TS/JS and Go. A language file lists one sample per
smell, a small change to a temporary repo that adds that smell, and `MatrixCase` proves each one is found and that the
list holds every smell the language can have. A smell added to config.py with no sample fails the language's test.
Sample code is built from rows and pieces: broom reads the tests too, and a suppression, a TODO or a skip written out
here would be a finding of this file."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import ContextManager, Dict, Optional, Tuple
from unittest import mock

from isolation import DEFAULT_DATA
from support import BroomCase

from broom.config import DEAD_CODE, SMELL_LIMITS, SMELL_PRESENCE
from broom import depcruise
from broom.depcruise import pick
from broom.smells import find_smells

EVERY_SMELL = {*SMELL_LIMITS, *SMELL_PRESENCE, DEAD_CODE}
# What the language itself rules out: Go has no ternary operator, and its compiler refuses a package cycle.
GO_EXEMPT = {"nested_ternary", "import_cycle", "folder_cycle"}
# Swift's compiler refuses modules that import one another; cycles between its folders aren't read yet.
SWIFT_EXEMPT = {"import_cycle", "folder_cycle"}
# Rust has no ternary operator either: `if` is an expression, and whether a nested one is the smell is not settled.
RUST_EXEMPT = {"nested_ternary"}


REAL_OWN = DEFAULT_DATA / "node"  # broom's own dependency-cruiser in the user's real data directory, read only


def real_copy() -> ContextManager:
    """A patch that makes broom's own dependency-cruiser the one installed in the user's real data directory, where
    it is: the test run's own data directory has none, and a sample of cycles between folders needs one that reads .ts."""
    return mock.patch.object(depcruise, "OWN_DIR", REAL_OWN)


def unusable(tool: str, repo: Path) -> Optional[str]:
    """Why `tool` can't measure on this machine for `repo`, or None when it can."""
    if tool == "depcruise":
        with real_copy():
            return None if pick(repo) else "no dependency-cruiser that reads .ts files: broom doctor has the fix"
    return None if shutil.which(tool) else f"{tool} missing"


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


def repeated(row: str, times: int) -> str:
    """`row` as `times` lines, `{i}` in it standing for the line's number: sized samples are made of these."""
    return "".join(row.replace("{i}", str(i)) + "\n" for i in range(times))


@dataclass(frozen=True)
class Sample:
    """A change that adds one smell: `change` is written after `base` is committed, and the smell must be reported for
    the first file of `change`. `tools` are the programs the smell is measured with: one that is missing or can't measure here skips the sample."""

    change: Dict[str, str]
    tools: Tuple[str, ...] = ()
    base: Dict[str, str] = field(default_factory=dict)


class MatrixCase(BroomCase):
    """One language's matrix. A subclass sets `EXEMPT` (the smells it is spared), `SCAFFOLD` (the files every repo of
    the language needs, as a go.mod) and `SAMPLES` (the smell and its sample)."""

    EXEMPT: set = set()
    SCAFFOLD: Dict[str, str] = {}
    SAMPLES: Dict[str, Sample] = {}

    def test_every_smell_the_language_can_have_has_a_sample(self) -> None:
        self.assertEqual(set(self.SAMPLES), EVERY_SMELL - self.EXEMPT)

    def test_each_sample_is_found(self) -> None:
        for smell, sample in self.SAMPLES.items():
            with self.subTest(smell):
                self.prove(smell, sample)

    def prove(self, smell: str, sample: Sample) -> None:
        """Commit the base, write the change and check `find_smells` reports `smell` for the first changed file."""
        r = self.repo({"README.md": "x\n", **self.SCAFFOLD, **sample.base})
        for rel, body in sample.change.items():
            (r / rel).parent.mkdir(parents=True, exist_ok=True)
            (r / rel).write_text(body)
        for tool in sample.tools:
            why = unusable(tool, r)
            if why:
                self.skipTest(why)
        with real_copy():
            found, _ = find_smells(r, [r / rel for rel in sample.change], "HEAD")
        mine = [s.metric for s in found if s.file == self.target(r, sample)]
        self.assertIn(smell, mine, f"found for {next(iter(sample.change))}: {sorted(set(mine))}")

    @staticmethod
    def target(repo: Path, sample: Sample) -> Path:
        """The file the smell is reported for."""
        return repo / next(iter(sample.change))
