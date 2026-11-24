"""Smells read from a syntax tree by ast-grep (decision 038). The rules are data: YAML files under
`defaults/sg/rules/`, one structural rule each, whose `metadata.smell` names the smell it finds. A rule matches nodes
of the tree, never text, so a string or a comment that looks like code is never taken for it.

`matches` runs every rule of broom's over some files and gives each match with the lines it spans and what its
metavariables caught. Without ast-grep it gives nothing and says so in a note, so a missing tool never blocks.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from .gitutil import run
from .state import DEFAULTS

SG_CONFIG = DEFAULTS / "sg" / "sgconfig.yml"
MISSING = "missing:ast-grep (brew install ast-grep)"
UNPARSED = "unparsed"  # the smell of each `*-unparsed` rule: a region of a file the grammar can't read
Span = Tuple[int, int]  # a first and a last line, 1-based


@dataclass(frozen=True)
class Match:
    """One node a rule matched: its file (as given), its first and last line (1-based), the rule's id, the smell its
    metadata names, its message, the text each single metavariable caught, and the bytes of the file it spans (its
    first, and the one after its last)."""

    file: str
    line: int
    end: int
    rule: str
    smell: str
    message: str = ""
    caught: Dict[str, str] = field(default_factory=dict)
    start: int = 0
    stop: int = 0

    @property
    def lines(self) -> int:
        """How many lines the matched node spans."""
        return self.end - self.line + 1


def parse(row: dict) -> Match:
    """A Match from one line of `ast-grep scan --json=stream --include-metadata`."""
    span = row.get("range") or {}
    at = span.get("byteOffset") or {}
    single = (row.get("metaVariables") or {}).get("single") or {}
    return Match(file=str(row.get("file", "")), line=int(span.get("start", {}).get("line", 0)) + 1,
                 end=int(span.get("end", {}).get("line", 0)) + 1, rule=str(row.get("ruleId", "")),
                 smell=str((row.get("metadata") or {}).get("smell", "")), message=str(row.get("message") or ""),
                 caught={k: str(v.get("text", "")) for k, v in single.items()},
                 start=int(at.get("start", 0)), stop=int(at.get("end", 0)))


@dataclass(frozen=True)
class Rules:
    """Which rules a run applies: those under `config`, narrowed to the ids the regular expression `only` matches
    (ast-grep's `--filter`), or all of them when it is empty. A run that needs a few rules pays for those alone."""

    config: Path = SG_CONFIG
    only: str = ""

    def args(self) -> List[str]:
        """The arguments of `ast-grep scan` that pick these rules."""
        return ["--config", str(self.config), *([f"--filter={self.only}"] if self.only else [])]


ALL = Rules()


def matches(root: Path, rels: List[str], notes: List[str], timeout: float, rules: Rules = ALL) -> List[Match]:
    """Every match of the `rules` in the files `rels` (relative to `root`). A missing ast-grep, a timeout or a
    failure gives nothing and a note."""
    if not rels:
        return []
    exe = shutil.which("ast-grep")
    if not exe:
        notes.append(MISSING)
        return []
    rc, out, err = run([exe, "scan", *rules.args(), "--json=stream", "--include-metadata", *rels], root,
                       timeout=timeout)
    if rc is None:
        notes.append("timeout:ast-grep reading the syntax tree")
        return []
    found: List[Match] = []
    for raw in out.split("\n"):  # not splitlines: JSON leaves a U+2028 or a U+0085 in a match's text as it is
        try:
            found.append(parse(json.loads(raw)))
        except (ValueError, TypeError, AttributeError):
            continue
    if rc not in (0, 1) and not found:
        notes.append(f"failed:ast-grep: {(err or out).strip()[:120]}")
    return found


def by_file(found: List[Match], rels: List[str]) -> Dict[str, List[Match]]:
    """The matches `found` per file, with an empty list for each of `rels` none was found in."""
    out: Dict[str, List[Match]] = {rel: [] for rel in rels}
    for m in found:
        out.setdefault(m.file, []).append(m)
    return out


def parsed(found: Dict[str, List[Match]], notes: List[str]) -> Dict[str, List[Match]]:
    """`found` (matches per file) less what lies in a region the grammar can't read, with a note for each file that
    holds one: a smell the parser can't see is not guessed (decision 038). The `*-unparsed` matches go too."""
    for rel, ms in found.items():
        broken = [(m.line, m.end) for m in ms if m.smell == UNPARSED]
        if broken:
            notes.append(f"ast-grep can't parse {rel} from line {broken[0][0]}: smells there go unmeasured")
            found[rel] = [m for m in ms if m.smell != UNPARSED and not inside(m.line, broken)]
    return found


def inside(line: int, among: List[Span]) -> bool:
    """Whether `line` lies in one of the spans."""
    return any(first <= line <= last for first, last in among)


def text_matches(texts: Dict[str, str], notes: List[str], timeout: float, rules: Rules) -> List[Match]:
    """`matches` for sources held in memory, `texts` (a relative path to its text): ast-grep reads files, so they are
    written to a scratch folder first, each at its path, which picks its language."""
    if not texts:
        return []
    with tempfile.TemporaryDirectory(prefix="broom-tree-") as tmp:
        for rel, text in texts.items():
            (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp) / rel).write_text(text, encoding="utf-8")
        return matches(Path(tmp), list(texts), notes, timeout, rules)
