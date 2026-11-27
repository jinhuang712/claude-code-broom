"""`broom stats` as text for a person: one short heading per section and plain aligned tables, no colour. The same data
is the `--json` object."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

from .gate import display
from .needs import LANG_NAMES
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


def language(r: dict) -> str:
    """A row's language as a person reads it, such as TS/JS for `js`; the JSON keeps the short name."""
    return LANG_NAMES.get(r["language"], r["language"])


def counts(r: dict) -> List[object]:
    """The four numbers of a size row: files and lines, then the same for tests."""
    return [r["files"], r["lines"], r["test_files"], r["test_lines"]]


def size_lines(d: dict) -> List[str]:
    """The size section: lines by language and by folder, the longest code files and the largest files of any kind."""
    head = ["files", "lines", "test files", "test lines"]
    total = [["total", *counts(d["total"])]]
    langs = table(["language", *head], [[language(r), *counts(r)] for r in d["languages"]] + total)
    folders = table(["folder", *head], [[r["folder"], *counts(r)] for r in d["folders"]])
    if d["more_folders"]:
        folders.append(f"  ... and {d['more_folders']} more folders; `--top N` lists more")
    longest = table(["longest files", "lines"], [[r["file"] + (" (test)" if r["test"] else ""), r["lines"]]
                                                 for r in d["longest"]])
    biggest = table(["largest files, any kind", "bytes"], [[r["file"], r["bytes"]] for r in d["largest_files"]])
    return section("Size (code lines)", d["note"], [langs, folders, longest, biggest])


def coverage_lines(c: dict) -> List[str]:
    """The coverage part of the tests section: the share of lines a test reached by the project's own report and the
    files with most lines none did; without a report, how a test run writes one."""
    if c["report"] is None:
        return ["  no coverage report found (coverage.xml, lcov.info, coverage.out or coverage.json); broom runs no tests.",
                *captioned("A test run writes one with:", [f"    {how}" for how in c["how"]])]
    if c["unread"]:
        return [f"  coverage: {c['report']} could not be read"]
    behind = " (written before the last change to the code it covers)" if c["behind"] else ""
    head = (f"  coverage: {c['percent']}% of {c['lines']} lines reached, by {c['report']}{behind}; "
            f"{c['unreached_files']} of {c['files']} files not reached at all")
    return [head, *table(["least reached", "lines", "not reached", "reached"],
                         [[r["file"], r["lines"], r["missed"], f"{r['percent']}%"] for r in c["least"]])]


def tests_lines(d: dict) -> List[str]:
    """The tests section: files, cases and skipped tests by language, the files with most skipped, the code files with no
    test file by name, and the coverage."""
    langs = table(["language", "test files", "cases", "skipped"],
                  [[language(r), r["files"], r["cases"], r["skipped"]] for r in d["languages"]])
    skipped = table(["most skipped", "skipped"], [[r["file"], r["count"]] for r in d["skipped_files"]])
    u = d["untested"]
    bare = [f"  {u['count']} of {u['of']} code files have no test file by name.", *PAIRING_TEXT]
    bare += table(["largest of them", "lines"], [[r["file"], r["lines"]] for r in u["largest"]])
    helpers = "" if d["with_cases"] == d["files"] else f" ({d['with_cases']} of them hold test cases)"
    total = [f"  {d['files']} test files{helpers}, {d['cases']} test cases, {d['skipped']} skipped"]
    return section("Tests", d["note"], [total, langs, skipped, bare if u["of"] else [], coverage_lines(d["coverage"])])


def todo_text(t: dict) -> str:
    """The TODO line of the rot section: the count."""
    if not t["total"]:
        return "  no TODO, FIXME, HACK or XXX comments"
    return f"  {t['total']} TODO, FIXME, HACK or XXX comments"


def counted_lines(part: dict, what: str) -> List[str]:
    """A count of `what` with the files holding most, as the rot section shows it."""
    return [f"  {part['total']} {what}",
            *table(["files with most", "count"], [[r["file"], r["count"]] for r in part["files"]])]


def links_lines(part: dict) -> List[str]:
    """The broken Markdown links as the rot section shows them: the count, then each link with where it points."""
    shown = len(part["links"])
    more = [f"  the first {shown}; --top shows more"] if shown < part["total"] else []
    rows = [[f"{r['file']}:{r['line']}", r["target"]] for r in part["links"]]
    return [f"  {part['total']} Markdown links to paths that don't exist",
            *table(["link", "points at"], rows, left=(0, 1)), *more]


def rot_lines(d: dict) -> List[str]:
    """The rot section: lint suppressions, TODO comments, skipped tests, unsafe code, broken Markdown links."""
    s, t = d["suppressions"], d["todos"]
    kinds = ", ".join(f"{k} {n}" for k, n in s["kinds"].items())
    suppressed = [f"  {s['total']} lint suppressions" + (f" ({kinds})" if kinds else "")]
    suppressed += table(["files with most", "count"], [[r["file"], r["count"]] for r in s["files"]])
    todos = [todo_text(t), *table(["files with most", "count"], [[r["file"], r["count"]] for r in t["files"]])]
    return section("Rot", d["note"], [suppressed, todos, [f"  {d['skipped_tests']} skipped tests"],
                                       counted_lines(d["unsafe_code"], "unsafe constructs"),
                                       links_lines(d["broken_links"])])


def history_lines(d: dict) -> List[str]:
    """The history section: the most changed files and the pairs that most often changed together."""
    files = table(["most changed files", "commits"], [[r["file"], r["commits"]] for r in d["files"]])
    pairs = captioned("changed in one commit together (commits of over 30 files left out):",
                      table(["pair", "commits"], [[" + ".join(r["files"]), r["commits"]] for r in d["pairs"]]))
    return section(f"History ({d['commits']} of the last {d['last_commits']} commits)", d["note"], [files, pairs])


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
    data = report(repo, [Path(p).resolve() for p in args.paths], args.top, args.commits)
    sys.stdout.write((json.dumps(data, indent=1) if args.json else render(data)) + "\n")
    return 0
