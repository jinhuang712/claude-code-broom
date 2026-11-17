"""The edit hook (PostToolUse on Edit, Write and Serena's edit tools): format per edit when format_on=edit, and record
the file for the turn's end when check_on=stop, a subagent's edit for that subagent's own end.

It runs after every edit, and most edits leave it nothing but a line to append. So what only some edits need (the
formatter) is loaded where it is used, not when the module is."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from .config import REPO_FILE, excluded, setting
from .gitutil import git_root
from .state import append_line
from .toolchain import lang_of
from .turns import note_config, turn_dir

SERENA_ONE_FILE = re.compile(
    r"^mcp__.*serena.*__(replace_symbol_body|insert_after_symbol|insert_before_symbol|replace_content|create_text_file)$"
)
SERENA_MANY_FILES = re.compile(r"^mcp__.*serena.*__(rename_symbol|replace_in_files|safe_delete_symbol)$")


def serena_path(rel: str, data: dict) -> Optional[Path]:
    """The path a Serena call names: as given if absolute, else found under its cwd or project; None if not."""
    p = Path(rel)
    if p.is_absolute():
        return p
    for base in (data.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR")):
        if base and (Path(base) / p).exists():
            return Path(base) / p
    return None


def edited_path(data: dict, sd: Path) -> Optional[Path]:
    """The one file the tool call in `data` changed, or None when it names none. A many-file edit through Serena
    names none: its repo is noted in `sd`, and the turn's end takes that repo's changed files instead."""
    tool = data.get("tool_name") or ""
    args = data.get("tool_input") or {}
    if tool in ("Edit", "Write", "MultiEdit"):
        return Path(args["file_path"]) if args.get("file_path") else None
    if SERENA_ONE_FILE.match(tool) and args.get("relative_path"):
        return serena_path(args["relative_path"], data)
    if SERENA_MANY_FILES.match(tool):
        cwd = Path(data.get("cwd") or os.getcwd()).resolve()
        root = git_root(cwd)
        if root and setting("check_on", cwd) == "stop":
            append_line(sd / "scan.txt", str(root))
    return None


def hook_edit(data: dict) -> None:
    """The edit hook: list the file a tool call changed for the stop check, and format it if format_on is edit."""
    sd = turn_dir(data)
    path = edited_path(data, sd)
    if path is None or not path.is_file():
        return
    path = path.resolve()
    if git_root(path.parent) is None or excluded(path):
        # Outside any repo is a scratch file, a draft script in a temp directory: no project's code. Ten style
        # findings in one subagent's draft once stopped its session's turn.
        return
    if path.name == REPO_FILE:
        note_config(path, sd)
    if setting("check_on", path) == "stop" and lang_of(path):
        append_line(sd / "edits.txt", str(path))
    if setting("format_on", path) == "edit":
        from .fmt import format_files  # the formatters, only for those who format at every edit

        # Claude Code shows Claude the diff of a file changed on disk since its last read, so no message here.
        format_files([path], final=False, scope=setting("format_scope", path))
