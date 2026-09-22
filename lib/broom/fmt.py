"""Formatting with each project's own formatter.

Go always gets gofmt (canonical everywhere) and Rust rustfmt. JS/TS and web files are formatted only when the
project configures biome, oxfmt or prettier, and Python only when it configures ruff, so a repo that doesn't
format never gets reformatted files.

The final pass (at commit) also applies the project's golangci formatters, goimports included. Per edit it
would delete an import Claude adds one edit before the code that uses it.

Scope `changed` keeps only the formatter's edits that touch changed lines, like an IDE's "only VCS changed
text": the file is formatted whole, then every hunk of the formatter's diff that doesn't overlap a changed line
is put back. That works with every formatter, including the ones without range support.
"""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

from .common import (
    GOLANGCI_CFG, JS_EXTS, PY_EXTS, WEB_EXTS, ChangedLines, boundary, find_up, js_formatter, resolve_bin,
    ruff_configured, run, rust_edition,
)


def golangci_formatters(path: Path, stop: Path) -> Optional[Path]:
    """The project's golangci config when it enables formatters."""
    cfg = find_up(path.parent, GOLANGCI_CFG, stop)
    try:
        return cfg if cfg and "formatters" in cfg.read_text() else None
    except OSError:
        return None


def formatter_cmd(path: Path, final: bool) -> Optional[Tuple[str, List[str], Path]]:
    """(tool name, command, cwd) that formats `path`, or None."""
    ext = path.suffix.lower()
    stop = boundary(path)
    if ext == ".go":
        cfg = golangci_formatters(path, stop) if final else None
        exe = shutil.which("golangci-lint") if cfg else None
        if cfg and exe:
            return "golangci-lint fmt", [exe, "fmt", "-c", str(cfg), str(path)], cfg.parent
        gofmt = shutil.which("gofmt")
        return ("gofmt", [gofmt, "-w", str(path)], path.parent) if gofmt else None
    if ext in JS_EXTS or ext in WEB_EXTS:
        found = js_formatter(path, stop)
        if not found:
            return None
        tool, cfg_dir = found
        exe = resolve_bin(tool, path.parent, stop)
        if not exe:
            return None
        if tool == "biome":
            return tool, [exe, "format", "--write", str(path)], cfg_dir
        if tool == "oxfmt":
            return tool, [exe, "--no-error-on-unmatched-pattern", str(path)], cfg_dir
        return tool, [exe, "--write", "--log-level", "silent", "--ignore-unknown", str(path)], cfg_dir
    if ext == ".rs":
        rustfmt = shutil.which("rustfmt")
        if not rustfmt:
            return None
        return "rustfmt", [rustfmt, "--edition", rust_edition(path, stop), str(path)], path.parent
    if ext in PY_EXTS and ruff_configured(path, stop):
        ruff = shutil.which("ruff")
        return ("ruff format", [ruff, "format", "--quiet", str(path)], path.parent) if ruff else None
    return None


def keep_hunks(before: str, after: str, changed: Set[int]) -> str:
    """`after`, with every formatter hunk that doesn't overlap a changed line (1-based, in `before`) undone."""
    old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)
    out: List[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            out += old[i1:i2]
            continue
        if i2 - i1 == j2 - j1:  # line-for-line (quotes, spacing): decide each line on its own
            out += [new[j1 + k] if i1 + k + 1 in changed else old[i1 + k] for k in range(i2 - i1)]
            continue
        # Lines re-wrapped or joined: the hunk goes in or stays out as a whole.
        # An insertion sits between lines i1 and i1 + 1; either neighbour being changed makes it count.
        touched = range(i1 + 1, i2 + 1) if i2 > i1 else (i1, i1 + 1)
        out += new[j1:j2] if any(n in changed for n in touched) else old[i1:i2]
    return "".join(out)


def format_file(path: Path, final: bool = True, lines: Optional[Set[int]] = None) -> Optional[str]:
    """Format in place; the tool's name when it changed the file. With `lines`, only the formatter's edits that
    touch those lines stay (None formats the whole file)."""
    found = formatter_cmd(path, final)
    if not found:
        return None
    tool, cmd, cwd = found
    try:
        before = path.read_text()
        run(cmd, cwd, timeout=30)
        after = path.read_text()
        if lines is not None and after != before:
            kept = keep_hunks(before, after, lines)
            if kept != after:
                path.write_text(kept)
                after = kept
        return tool if after != before else None
    except (OSError, UnicodeDecodeError):
        return None


def format_files(paths: Iterable[Path], final: bool = True, scope: str = "file",
                 changed: Optional[ChangedLines] = None) -> List[Tuple[Path, str]]:
    """(path, tool) for every file a formatter changed. Scope `changed` limits each file to its changed lines,
    measured by `changed` (against HEAD by default); a new file counts whole."""
    changed = changed or ChangedLines()
    out = []
    for p in paths:
        tool = format_file(p, final, changed.get(p) if scope == "changed" else None)
        if tool:
            out.append((p, tool))
    return out
