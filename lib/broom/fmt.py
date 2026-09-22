"""Formatting with each project's own formatter.

Go always gets gofmt (canonical everywhere) and Rust rustfmt. JS/TS and web files are formatted only when the
project configures biome, oxfmt or prettier, and Python only when it configures ruff, so a repo that doesn't
format never gets reformatted files.

The final pass (at commit) also applies the project's golangci formatters, goimports included. Per edit it
would delete an import Claude adds one edit before the code that uses it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .common import (
    GOLANGCI_CFG, JS_EXTS, PY_EXTS, WEB_EXTS, boundary, find_up, js_formatter, resolve_bin, ruff_configured, run,
    rust_edition,
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


def format_file(path: Path, final: bool = True) -> Optional[str]:
    """Format in place; the tool's name when it changed the file."""
    found = formatter_cmd(path, final)
    if not found:
        return None
    tool, cmd, cwd = found
    try:
        before = path.read_bytes()
        run(cmd, cwd, timeout=30)
        return tool if path.read_bytes() != before else None
    except OSError:
        return None


def format_files(paths: Iterable[Path], final: bool = True) -> List[Tuple[Path, str]]:
    """(path, tool) for every file a formatter changed."""
    changed = []
    for p in paths:
        tool = format_file(p, final)
        if tool:
            changed.append((p, tool))
    return changed
