"""Self-waivers: changes that loosen the bar. A change that turns a smell off, raises a limit or excludes a path in
`.broom.json`, one that adds a lint suppression, and a `git commit --no-verify` are each written to the ledger and shown
in the turn's summary. None of them blocks anything.

A waiver is a dict (kind, repo, file, note, key) that `ledger.waived` writes. The key makes the same waiver, seen
again by a later check of the same turn, count once.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import ledger
from .config import REPO_FILE, SMELL_LIMITS
from .gitcmd import GitOp, parse_commit
from .gitutil import ChangedLines, git, git_root
from .smells import moved
from .state import parse_jsonc, read_jsonc, short_hash
from .treefacts import comment_trees

# What a lint suppression looks like: the tool's own marker. It is tested only on a comment, or on a Rust `allow`
# attribute, that a syntax tree isolated (treefacts.comment_trees), so a marker in a string never counts. Each is
# on a line without a comment sign before it, or this file would hold suppressions itself.
MARKERS = re.compile("|".join((
    r"\bnoqa\b", r"type:\s*ignore", "eslint-disable", "oxlint-disable", "@ts-ignore", "@ts-expect-error",
    r"\bnolint\b", "swiftlint:disable", "biome-ignore", "stylelint-disable",
    r"[#]!?\[allow\(",
)))
MARKER_WORDS = ("noqa", "ignore", "disable", "nolint", "@ts-", "allow(")  # a word each marker holds
NO_VERIFY_NOTE = "git commit --no-verify"


def waiver(kind: str, repo: str, file: str, note: str, text: str = "") -> dict:
    """One waiver. `text` tells two of the same kind, file and note apart (the line of a suppression, the command of a
    `--no-verify`)."""
    return {"kind": kind, "repo": repo, "file": file, "note": note,
            "key": short_hash(f"{kind}|{repo}|{file}|{note}|{text}")}


# ---------------------------------------------------------------- suppressions


def has_words(text: str, added: Optional[Set[int]]) -> bool:
    """Whether a line of `text` the change added (every line when `added` is None) holds a word of a suppression
    marker: what a file needs before its tree is read, since a marker on an added line is in that line's text."""
    rows = text.splitlines()
    return any(word in rows[n - 1] for n in (added if added is not None else range(1, len(rows) + 1))
               if 0 < n <= len(rows) for word in MARKER_WORDS)


def suppression_waivers(root: Path, files: List[Path], changed: ChangedLines) -> List[dict]:
    """A waiver for each comment (or Rust `allow` attribute) on a line the change added that is a suppression, in
    `files` of the repo at `root`. Only a file whose text holds a marker's word asks git which of its lines changed,
    and only one whose added lines hold one has its tree read."""
    texts: Dict[str, str] = {}
    lines: Dict[str, Tuple[Path, Optional[Set[int]]]] = {}
    for f in files:
        try:
            text = f.read_text(errors="replace")
            rel = f.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
        if any(word in text for word in MARKER_WORDS) and has_words(text, changed.get(f)):
            texts[rel], lines[rel] = text, (f, changed.get(f))
    out = []
    for rel, comments in comment_trees(root, texts, []).items():
        f, added = lines[rel]
        repo, shown = ledger.locate(f)
        rows = texts[rel].splitlines()
        for n, comment in sorted(comments.items()):
            marker = MARKERS.search(comment) if added is None or n in added else None
            if marker:  # the line's text only tells two waivers of one file apart: an identity, not a reading
                line = rows[n - 1].strip() if n <= len(rows) else comment
                out.append(waiver("suppression", repo, shown, marker.group(), line))
    return out


# ---------------------------------------------------------------- .broom.json


def listed(value: object) -> list:
    """`value` when it is a list, else an empty one."""
    return value if isinstance(value, list) else []


def raised_limits(old: dict, new: dict) -> List[str]:
    """The limits `new` (a .broom.json) sets higher than `old`'s do, as notes: `limits function_lines 50/100 ->
    80/150`. `test_limits` count against the test limits `old` had, which start from its `limits`."""
    before = moved(SMELL_LIMITS, old.get("limits"))
    after = moved(SMELL_LIMITS, new.get("limits"))
    notes = [f"limits {k} {before[k][0]}/{before[k][1]} -> {after[k][0]}/{after[k][1]}"
             for k in after if after[k] > before[k] and (after[k][0] > before[k][0] or after[k][1] > before[k][1])]
    was = moved(before, old.get("test_limits"))
    now = moved(after, new.get("test_limits"))
    notes += [f"test_limits {k} {was[k][0]}/{was[k][1]} -> {now[k][0]}/{now[k][1]}"
              for k in now if k in (new.get("test_limits") or {}) and now[k] != was[k]
              and (now[k][0] > was[k][0] or now[k][1] > was[k][1])]
    return notes


def loosened(old: dict, new: dict) -> List[str]:
    """What the .broom.json `new` loosens against `old`, as short notes such as `smells_off +magic_numbers`: smells
    turned off, globs added to `exclude` or `legacy`, commands added to `test_commands` (any of them makes a test run),
    limits raised, and `check_on` or `smells` set to off. Tightening is not a waiver."""
    notes = []
    for key in ("smells_off", "exclude", "legacy", "test_commands"):
        added = [str(x) for x in listed(new.get(key)) if x not in listed(old.get(key))]
        if added:
            notes.append(f"{key} " + " ".join(f"+{x}" for x in added))
    notes += raised_limits(old, new)
    for key in ("check_on", "smells"):
        if str(new.get(key, "")).strip().lower() == "off" and str(old.get(key, "")).strip().lower() != "off":
            notes.append(f"{key} off")
    return notes


def config_waivers(root: Path, base: str) -> List[dict]:
    """A waiver for each way the repo's own .broom.json, at `root`, loosens the bar against its content at `base`.
    One git process, and only for a repo that has the file."""
    path = root / REPO_FILE
    if not path.is_file():
        return []
    old = parse_jsonc(git(["show", f"{base}:{REPO_FILE}"], root) or "")
    repo, rel = ledger.locate(path)
    return [waiver("config", repo, rel, note) for note in loosened(old, read_jsonc(path))]


# ---------------------------------------------------------------- what a check or a command shows


def detect(groups: Dict[Path, List[Path]], changed: ChangedLines, base: str) -> List[dict]:
    """The waivers in what a check covers: `groups` is its files by repo, `changed` their changed lines and `base`
    what they are measured against."""
    found = [w for root, files in groups.items() for w in suppression_waivers(root, files, changed)]
    return found + [w for root in groups for w in config_waivers(root, base)]


def no_verify_waivers(ops: List[GitOp], command: str) -> List[dict]:
    """A waiver for each `git commit --no-verify` in the Bash `command` (`ops` is what gitcmd.parse found in it)."""
    out = []
    for op in ops:
        spec = parse_commit(op) if op.kind == "commit" else None
        root = git_root(spec.cwd) if spec and spec.no_verify and not spec.dry_run else None
        if root:
            out.append(waiver("no-verify", ledger.repo_of(root), "", NO_VERIFY_NOTE, command))
    return out
