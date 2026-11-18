"""A turn that changed code shows that tests ran (F2.13): broom looks for the trace of a test run and runs no test itself.

How the trace is found. Claude Code tells a hook what happened to a Bash command by which event fires, and broom
already sees every Bash call before it runs (the PreToolUse hook, hooks/commit.sh). So:

- started: the PreToolUse hook notes a command that is a test run (testcmd) for the session's turn: a line with the time
  and the command in the turn's `test-runs.jsonl`, as edits and asks are noted. No hook runs after every Bash call.
- failed: PostToolUseFailure fires after a command that exited non-zero, and notes the same command with its error's first
  line (`Exit code 1`). A test command that started and has no such note after it counts as passed.

At the turn's end (`findings`, from turncheck) a main session's turn that changed code in a repo that tracks a test file
is told, like any finding that stops a turn's end, when no test command started after the last change to the code
(`tests_not_run`), or when the last one started was noted as failed (`tests_failed`). The findings pass fixed, or by an
accept or a question put to the user, as every finding does; an accept holds for its turn only (`ACCEPTED_HERE`) and is
never a known issue.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import ledger
from .config import TESTS_FAILED, TESTS_NOT_RUN, TESTS_TOOL, repo_config, setting
from .findings import Issue
from .gitutil import git, git_root
from .state import append_line, session_dir
from .testcmd import is_test_run

MAX_COMMAND = 500  # characters of a command a note keeps
MAX_SHOWN = 100  # characters of a command a finding shows
MAX_ERROR = 80  # characters of an error's first line a note keeps
NOT_RUN = "no test ran after the last change to code"


def command_of(data: dict) -> str:
    """The Bash command of a tool call's hook input."""
    command = (data.get("tool_input") or {}).get("command")
    return command if isinstance(command, str) else ""


def watched(data: dict, command: str) -> bool:
    """Whether the hook's `command` is a test run broom notes: one that is, in a repo that checks at a turn's end."""
    cwd = Path(data.get("cwd") or os.getcwd())
    return is_test_run(command, repo_config(cwd).get("test_commands")) and setting("check_on", cwd) == "stop"


def note_run(data: dict, command: str, **more: object) -> None:
    """Note a test command in the session's turn: the time, the command and what `more` says (`exit`, for a failure). It
    goes in the session's directory, not a subagent's own, so that the main session's end sees what a subagent ran."""
    row = {"t": time.time(), "cmd": command[:MAX_COMMAND], **more}
    append_line(session_dir(data.get("session_id") or "cli") / ledger.RUNS, json.dumps(row))


def hook_pre_bash(data: dict) -> None:
    """PreToolUse on Bash, for every call that could be a commit or a test run (hooks/commit.sh lets the rest leave): check
    the commit in the command, if there is one, and note a test run for the turn unless the commit's denial keeps the
    command from running."""
    command = command_of(data)
    denied = False
    if "git" in command and "commit" in command:
        from .commitgate import hook_commit  # the linters and the gate: only for a command that may commit

        denied = hook_commit(data)
    if command and not denied and watched(data, command):
        note_run(data, command)


def hook_failed(data: dict) -> None:
    """PostToolUseFailure on Bash: note that a test command failed, with the first line of its error (`Exit code 1`)."""
    command = command_of(data)
    if not command or not watched(data, command):
        return
    error = str(data.get("error") or "").strip().splitlines()
    note_run(data, command, exit=(error[0] if error else "failed")[:MAX_ERROR])


# ---------------------------------------------------------------- at a turn's end


def runs_of(d: Path) -> List[dict]:
    """The test runs noted in the turn in `d`: a row with `t` and `cmd` for each that started, and one with `exit` besides
    for each that failed, in the order they were noted."""
    return [r for r in ledger.read(d / ledger.RUNS) if isinstance(r.get("t"), (int, float)) and "cmd" in r]


def accepted_here(d: Path) -> Set[str]:
    """The keys of the findings accepted for the turn in `d` only, which `broom known --accept` noted there."""
    return {r["key"] for r in ledger.read(d / ledger.ACCEPTED_HERE) if r.get("key")}


def tracks_tests(repo: Path) -> bool:
    """Whether the repo tracks a test file (testrot.TEST_FILE) of its own: one in a dependency or a generated folder
    (`vendor/`, `testdata/`) is no test of the project. Rust keeps its unit tests beside the code, which no name shows, so a
    Rust repo counts by its `tests/` folder alone."""
    from .maintained import DEPENDENCY_DIRS, GENERATED_DIRS
    from .testrot import TEST_FILE

    named = git(["ls-files", "-z", "--", "*test*", "*Test*"], repo) or ""
    skipped = DEPENDENCY_DIRS | GENERATED_DIRS
    return any(TEST_FILE.search(name) and not skipped & set(name.split("/")[:-1]) for name in named.split("\0"))


def last_change(files: List[Path]) -> float:
    """When the last of `files` was written; 0 for none that can be read."""
    times = []
    for f in files:
        try:
            times.append(f.stat().st_mtime)
        except OSError:
            pass
    return max(times, default=0.0)


def one_line(command: str) -> str:
    """The first line of a command, cut to MAX_SHOWN characters."""
    first = command.strip().splitlines()[0] if command.strip() else ""
    return first if len(first) <= MAX_SHOWN else first[:MAX_SHOWN] + "..."


def verdict(rows: List[dict], since: float) -> Optional[Tuple[str, str]]:
    """The rule and the message of what the test runs in `rows` show about the code last changed at `since`: no test
    started after it, or the last one that started failed; None when tests ran and passed."""
    starts = [r for r in rows if "exit" not in r and r["t"] > since]
    if not starts:
        return TESTS_NOT_RUN, NOT_RUN
    last = max(starts, key=lambda r: r["t"])
    failed = [r for r in rows if "exit" in r and r["cmd"] == last["cmd"] and r["t"] >= last["t"]]
    if failed:
        return TESTS_FAILED, f"the last test run failed: {failed[-1]['exit']}, `{one_line(last['cmd'])}`"
    return None


def off_here(repo: Path) -> bool:
    """Whether the repo turned the rule off: `tests_not_run` among the `smells_off` of its .broom.json."""
    off = repo_config(repo).get("smells_off")
    return isinstance(off, list) and TESTS_NOT_RUN in off


def repo_finding(repo: Path, files: List[Path], rows: List[dict]) -> Optional[Issue]:
    """The finding for a repo whose code `files` the turn changed, or None. It sits on the first of the files: the one a
    later edit of another file moves no finding from."""
    if off_here(repo) or not tracks_tests(repo):
        return None
    found = verdict(rows, last_change(files))
    return Issue(TESTS_TOOL, repo, files[0], 0, 0, found[0], found[1]) if found else None


def findings(d: Path, root: Optional[Path], files: List[Path]) -> List[Issue]:
    """The findings of a turn's end for the code `files` the turn in `d` changed: none for a subagent (`root` is None), for
    a repo that turned the rule off or tracks no test file, or where tests ran after the last change and passed. A finding
    the turn accepted is left out."""
    if root is None:
        return []
    from .gate import issue_key

    by_repo: Dict[Path, List[Path]] = {}
    for f in files:
        repo = git_root(f.parent)
        if repo:
            by_repo.setdefault(repo, []).append(f)
    rows, accepted = runs_of(d), accepted_here(d)
    found = (repo_finding(repo, group, rows) for repo, group in by_repo.items())
    return [i for i in found if i is not None and issue_key(i) not in accepted]
