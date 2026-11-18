"""What broom does with one file right after Claude edited it: format it where the project formats, and run the
linters that judge one file in milliseconds. It only tells Claude what it found, and never blocks.

Only what takes tens of milliseconds on one file runs here: ruff, oxlint without its type-aware rules, and SwiftLint.
What needs a build or a package (clippy, golangci-lint, tsc, swift build), a Node start with a project's own plugins
(ESLint, stylelint) or the whole repo waits for the commit. The edit hook is on the path of every edit, so each tool
gets a short time of its own, and a tool that is missing, slow or failing says nothing.

What counts is what the commit check counts (gate.select): a finding on a line that differs from HEAD, that nobody
accepted as known. A finding is told once for a file in a session, and again only after it went away and came back."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from .config import setting
from .gitutil import ChangedLines, git_root
from .state import emit, load_json, update_json
from .toolchain import boundary, js_linters, lang_of, py_root, swift_linter

if TYPE_CHECKING:  # only the annotations name them: an edit with nothing to lint loads no dataclasses
    from .findings import Findings, Issue

TOOL_SECONDS = 2  # what a formatter or a linter may take after an edit: a hung one must not hold the edit
SHOWN = 5  # the findings a message names; the rest it counts
TOLD = "told.json"  # {file: [the keys of the findings in it, as the last check found them]}, in the turn's directory
OXLINT = ("oxlint", "oxlint-default")  # the oxlint of a project's own config, and of broom's defaults


def format_after_edit(path: Path, changed: ChangedLines) -> bool:
    """Format `path` with the project's formatter in the format_scope the user set; whether the file changed. Where the
    project has no formatter for it nothing runs, and git is not asked."""
    from .fmt import format_file, formatter_cmd, lines_to_keep  # the formatters, only for those who format at every edit

    if formatter_cmd(path, final=False) is None:
        return False
    lines, _ = lines_to_keep([path], setting("format_scope", path), changed, final=False)
    return bool(format_file(path, final=False, lines=lines[path], timeout=TOOL_SECONDS))


def lint_python(path: Path, stop: Path) -> Findings:
    """ruff on the file, in the project's own config, or ruff's defaults where it has none."""
    from .langlint import check_python

    return check_python(py_root(path, stop), [path], timeout=TOOL_SECONDS)


def lint_js(path: Path, stop: Path) -> Findings:
    """oxlint on the file, in the project's own config or broom's defaults, without the type-aware rules that start a
    type check. A project that lints with ESLint or biome only gets nothing here: those start Node, or are no fast
    tool measured, and the commit check runs them."""
    from .weblint import oxlint_command, run_oxlint

    for tool, cfg_dir in js_linters(path, stop):
        if tool in OXLINT:
            cmd = oxlint_command(cfg_dir, stop, defaults=tool == "oxlint-default", type_aware=False)
            return run_oxlint([*cmd, str(path)], cfg_dir, TOOL_SECONDS) if cmd else ([], ["missing:oxlint"])
    return [], []


def lint_swift(path: Path, stop: Path) -> Findings:
    """SwiftLint on the file, in the project's own config or broom's defaults."""
    from .langlint import check_swiftlint

    tool, cfg_dir = swift_linter(path, stop)
    return check_swiftlint(cfg_dir, [path], defaults=tool == "swiftlint-default", timeout=TOOL_SECONDS)


LINTERS: Dict[str, Callable[[Path, Path], Findings]] = {"py": lint_python, "js": lint_js, "swift": lint_swift}


def fresh_findings(sd: Path, path: Path, found: List[Issue]) -> List[Issue]:
    """The findings in `found` not told before for `path`, and the record in `sd` of what is there now: what went
    away is forgotten, so a finding that comes back is told again."""
    if not found and str(path) not in load_json(sd / TOLD, {}):
        return []  # nothing there, nothing told before: no record to keep
    from .gate import issue_key  # the key of a finding, by the text of its line, so it stays when lines above move

    keys = {issue_key(i): i for i in found}
    fresh: List[Issue] = []

    def keep(told: dict) -> dict:
        fresh[:] = [i for k, i in keys.items() if k not in told.get(str(path), [])]
        if keys:
            told[str(path)] = sorted(keys)
        else:
            told.pop(str(path), None)
        return told

    update_json(sd / TOLD, {}, keep)
    return fresh


def message(path: Path, found: List[Issue]) -> str:
    """The line Claude reads: how many findings are on the lines it changed, the first few, and how many more."""
    from .gate import rel

    root = git_root(path.parent)
    name = rel(path, root) if root else path.name
    ordered = sorted(found, key=lambda i: (i.line, i.col))
    rows = [f"{name}:{i.line} {i.rule} {i.msg}" for i in ordered[:SHOWN]]
    more = f"; and {len(ordered) - SHOWN} more" if len(ordered) > SHOWN else ""
    return f"broom: {len(ordered)} finding(s) on the lines you changed in {name}: " + "; ".join(rows) + more


def light_check(path: Path, sd: Path, changed: ChangedLines) -> Optional[str]:
    """What to tell Claude of `path` after an edit: the findings of the fast linter on lines that differ from HEAD,
    that it wasn't told before. None when there are none, or when the linter could not run."""
    linter = LINTERS.get(lang_of(path) or "")
    if linter is None:
        return None
    found, notes = linter(path, boundary(path))
    if notes:  # missing, timed out or failed: no verdict, and what was told before stands
        return None
    if found:
        from .gate import baseline_keys, select

        found = select(found, {path}, baseline_keys(), changed)
    fresh = fresh_findings(sd, path, found)
    return message(path, fresh) if fresh else None


def after_edit(path: Path, sd: Path, *, format_it: bool, check_it: bool) -> None:
    """Format the file just edited when `format_it`, then, when `check_it`, tell Claude what its fast linter finds on
    the lines changed. The answer is context for Claude, never a block."""
    changed = ChangedLines()
    if format_it and format_after_edit(path, changed):
        changed.forget(path)  # the formatter moved lines: what differs from HEAD is asked again, for this file
    text = light_check(path, sd, changed) if check_it else None
    if text:
        emit({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}})
