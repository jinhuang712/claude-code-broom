"""`broom stats` as text for a person: one short heading per section and plain aligned tables, no colour. The same data
is the `--json` object."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

from .gate import display
from .stats import report

PAIRING_TEXT = ["  The pairing goes by file name: foo.py with test_foo.py or foo_test.py, foo.go with foo_test.go,",
                "  foo.ts with foo.test.ts or foo.spec.ts, Foo.swift with FooTests.swift; a test file anywhere counts."]


def table(head: Sequence[str], rows: Iterable[Sequence[object]], left: Sequence[int] = (0,)) -> List[str]:
    """Aligned lines for a table, indented by two: the columns in `left` are left-aligned, the others right-aligned.
    Nothing for no rows."""
    grid = [[str(c) for c in row] for row in [head, *rows]]
    if len(grid) == 1:
        return []
    widths = [max(len(row[i]) for row in grid) for i in range(len(head))]
    return ["  " + "  ".join(c.ljust(w) if i in left else c.rjust(w) for i, (c, w) in enumerate(zip(row, widths))).rstrip()
            for row in grid]


def captioned(caption: str, rows: List[str]) -> List[str]:
    """A line of text over table `rows`; nothing when there are no rows."""
    return [f"  {caption}", *rows] if rows else []


def section(title: str, note: object, blocks: List[List[str]]) -> List[str]:
    """A heading, the note if the question couldn't be answered fully, then the non-empty blocks apart by a blank line."""
    out = [title] + ([f"  note: {note}"] if note else [])
    for i, block in enumerate(b for b in blocks if b):
        out += ["", *block] if i or note else block
    return out


def counts(r: dict) -> List[object]:
    """The four numbers of a size row: files and lines, then the same for tests."""
    return [r["files"], r["lines"], r["test_files"], r["test_lines"]]


def size_lines(d: dict) -> List[str]:
    """The size section: lines by language and by folder, and the longest files."""
    head = ["files", "lines", "test files", "test lines"]
    total = [["total", *counts(d["total"])]]
    langs = table(["language", *head], [[r["language"], *counts(r)] for r in d["languages"]] + total)
    folders = table(["folder", *head], [[r["folder"], *counts(r)] for r in d["folders"]])
    if d["more_folders"]:
        folders.append(f"  ... and {d['more_folders']} more folders; `--top N` lists more")
    longest = table(["longest files", "lines"], [[r["file"] + (" (test)" if r["test"] else ""), r["lines"]]
                                                 for r in d["longest"]])
    return section("Size (non-blank lines)", d["note"], [langs, folders, longest])


def tests_lines(d: dict) -> List[str]:
    """The tests section: files, cases and skipped tests by language, the files with most skipped, and the code files with no
    test file by name."""
    langs = table(["language", "test files", "cases", "skipped"],
                  [[r["language"], r["files"], r["cases"], r["skipped"]] for r in d["languages"]])
    skipped = table(["most skipped", "skipped"], [[r["file"], r["count"]] for r in d["skipped_files"]])
    u = d["untested"]
    bare = [f"  {u['count']} of {u['of']} code files have no test file by name.", *PAIRING_TEXT]
    bare += table(["largest of them", "lines"], [[r["file"], r["lines"]] for r in u["largest"]])
    total = [f"  {d['files']} test files, {d['cases']} test cases, {d['skipped']} skipped"]
    return section("Tests", d["note"], [total, langs, skipped, bare if u["of"] else []])


def todo_text(t: dict) -> str:
    """The TODO line of the rot section: the count, and how many of the blamed lines are old; the cap said when it cut."""
    if not t["total"]:
        return "  no TODO, FIXME, HACK or XXX comments"
    age = (f"{t['older']} of {t['blamed']} blamed are older than {t['older_than_days']} days by git blame"
           if t["blamed"] else "none blamed: not committed yet")
    cap = f" (blame stops at {t['blamed']} lines, in the files with most)" if t["capped"] else ""
    return f"  {t['total']} TODO, FIXME, HACK or XXX comments, {age}{cap}"


def rot_lines(d: dict) -> List[str]:
    """The rot section: lint suppressions, TODO comments with their age, skipped tests."""
    s, t = d["suppressions"], d["todos"]
    kinds = ", ".join(f"{k} {n}" for k, n in s["kinds"].items())
    suppressed = [f"  {s['total']} lint suppressions" + (f" ({kinds})" if kinds else "")]
    suppressed += table(["files with most", "count"], [[r["file"], r["count"]] for r in s["files"]])
    todos = [todo_text(t), *table(["files with most", "count"], [[r["file"], r["count"]] for r in t["files"]])]
    return section("Rot", d["note"], [suppressed, todos, [f"  {d['skipped_tests']} skipped tests"]])


def history_lines(d: dict) -> List[str]:
    """The history section: the most changed files and the pairs that most often changed together."""
    files = table(["most changed files", "commits"], [[r["file"], r["commits"]] for r in d["files"]])
    pairs = captioned("changed in one commit together (commits of over 30 files left out):",
                      table(["pair", "commits"], [[" + ".join(r["files"]), r["commits"]] for r in d["pairs"]]))
    return section(f"History (last {d['days']} days, {d['commits']} commits)", d["note"], [files, pairs])


def render(data: dict) -> str:
    """The text for `data` (from `report`): a line naming the repo and the paths, then the four sections."""
    narrowed = f", narrowed to {', '.join(data['paths'])}" if data["paths"] else ""
    out = [f"broom stats: {display(Path(data['repo']))}{narrowed}, {data['files']} code files read"]
    for lines in (size_lines(data["size"]), tests_lines(data["tests"]), rot_lines(data["rot"]),
                  history_lines(data["history"])):
        out += ["", *lines]
    return "\n".join(out)


def run(repo: Path, args: argparse.Namespace) -> int:
    """Print the stats of `repo`, narrowed to `args.paths`, as text or as JSON with `--json`."""
    data = report(repo, [Path(p).resolve() for p in args.paths], args.top, args.days)
    sys.stdout.write((json.dumps(data, indent=1) if args.json else render(data)) + "\n")
    return 0
