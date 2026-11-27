"""A turn that changed code shows that tests ran (F2.13): broom looks for the trace of a test run and runs no test itself.

How the trace is found. Claude Code tells a hook what happened to a Bash command by which event fires, and broom
already sees every Bash call before it runs (the PreToolUse hook, hooks/commit.sh). So:

- started: the PreToolUse hook notes a command that is a test run (testcmd) for the session: a line with the time, the
  command and what content it tests (testtree) in the session's `test-runs.jsonl`, kept across its turns (the newest
  MAX_RUNS), since content tested at an earlier turn is tested. No hook runs after every Bash call.
- failed: PostToolUseFailure fires after a command that exited non-zero, and notes the same command with its error's first
  line (`Exit code 1`). A test command that started and has no such note after it counts as passed.

At the turn's end (`findings`, from turncheck) a main session's turn that changed code in a repo that tracks a test file
is told, like any finding that stops a turn's end, when a file it changed has no passing test run on its current content
(`tests_not_run`), or when the last test run, by time, failed (`tests_failed`). Content is judged by blob id, not by
modification time (testtree). The findings pass fixed, or by an accept or a question put to the user, as every finding
does; an accept holds for its turn only (`ACCEPTED_HERE`) and is never a known issue.
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
from .gitutil import git, git_root, main_worktree
from .passed import rel_paths, worktree_blobs
from .state import append_line, read_lines, session_dir
from .testcmd import test_dirs

MAX_COMMAND = 500  # characters of a command a note keeps
MAX_SHOWN = 100  # characters of a command a finding shows
MAX_ERROR = 80  # characters of an error's first line a note keeps
MAX_NAMED = 3  # files a finding names before "and N more"
MAX_RUNS = 200  # the test-run notes a session keeps, the newest: they outlive the turn
NOT_RUN = "no test ran after the last change to code"


def command_of(data: dict) -> str:
    """The Bash command of a tool call's hook input."""
    command = (data.get("tool_input") or {}).get("command")
    return command if isinstance(command, str) else ""


def run_dirs(data: dict, command: str) -> List[Path]:
    """Where the hook's `command` runs tests, which broom notes: empty for a command that runs none, and in a repo that
    doesn't check at a turn's end."""
    cwd = Path(data.get("cwd") or os.getcwd())
    if setting("check_on", cwd) != "stop":
        return []
    return test_dirs(command, cwd, repo_config(cwd).get("test_commands"))


def note_run(data: dict, command: str, **more: object) -> None:
    """Note a test command in the session, for its turns to come: the time, the command and what `more` says (the content a start tests,
    the `exit` of a failure). It goes in the session's directory, not a subagent's own, so that the main session's end sees
    what a subagent ran."""
    row = {"t": time.time(), "cmd": command[:MAX_COMMAND], **more}
    path = session_dir(data.get("session_id") or "cli") / ledger.RUNS
    append_line(path, json.dumps(row))
    rows = read_lines(path)
    if len(rows) > MAX_RUNS:
        path.write_text("".join(f"{r}\n" for r in rows[-MAX_RUNS:]))


def note_start(data: dict, command: str, dirs: List[Path]) -> None:
    """Note a test run that starts in the directories `dirs`, with what content it tests in the repo of each."""
    from .testtree import snapshot  # the work tree is read only for a test run

    roots = dict.fromkeys(root for root in (git_root(d) for d in dirs) if root)
    note_run(data, command, repos=[snapshot(root) for root in roots])


def hook_pre_bash(data: dict) -> None:
    """PreToolUse on Bash, for every call that could be a commit or a test run (hooks/commit.sh lets the rest leave): check
    the commit in the command, if there is one, and note a test run for the turn unless the commit's denial keeps the
    command from running."""
    command = command_of(data)
    denied = False
    if "git" in command and "commit" in command:
        from .commitgate import hook_commit  # the linters and the gate: only for a command that may commit

        denied = hook_commit(data)
    dirs = [] if denied or not command else run_dirs(data, command)
    if dirs:
        note_start(data, command, dirs)


def hook_failed(data: dict) -> None:
    """PostToolUseFailure on Bash: note that a test command failed, with the first line of its error (`Exit code 1`)."""
    command = command_of(data)
    if command and run_dirs(data, command):
        error = str(data.get("error") or "").strip().splitlines()
        note_run(data, command, exit=(error[0] if error else "failed")[:MAX_ERROR])


# ---------------------------------------------------------------- at a turn's end


def runs_of(d: Path) -> List[dict]:
    """The test runs noted in the session of the turn in `d`, its earlier turns' too: a row with `t`, `cmd` and `repos` for each that started, and one with `exit`
    besides for each that failed, in the order they were noted."""
    return [r for r in ledger.read(d / ledger.RUNS) if isinstance(r.get("t"), (int, float)) and "cmd" in r]


def accepted_rows(d: Path) -> List[dict]:
    """What `broom known --accept` noted for the turn in `d` alone: a row with the `key` and the `rule` of each finding."""
    return list(ledger.read(d / ledger.ACCEPTED_HERE))


def accepted_here(d: Path) -> Set[str]:
    """The keys of the findings accepted for the turn in `d` only."""
    return {r["key"] for r in accepted_rows(d) if r.get("key")}


def test_runs(rows: List[dict], root: Path) -> List[dict]:
    """The test runs of the repo whose work tree is at `root` that the `rows` of a session tell, oldest first: each with its
    `exit` (None for one that didn't fail), its `cmd`, and the `head` and `dirty` blobs it tested there. A failure note
    belongs to the last run of its command that started before it. A run in another repo, or in none, is left out. The
    worktrees of one repo are one repo."""
    starts = sorted((r for r in rows if "exit" not in r), key=lambda r: r["t"])
    exits: Dict[int, object] = {}
    for fail in (r for r in rows if "exit" in r):
        before = [i for i, s in enumerate(starts) if s["cmd"] == fail["cmd"] and s["t"] <= fail["t"]]
        if before:
            exits[before[-1]] = fail["exit"]
    main = str(main_worktree(root))
    return [{"cmd": s["cmd"], "exit": exits.get(i), "head": snap.get("head"), "dirty": snap.get("dirty")}
            for i, s in enumerate(starts) for snap in s.get("repos") or [] if snap.get("main") == main]


def tracks_tests(repo: Path) -> bool:
    """Whether the repo tracks a test file (testrot.TEST_FILE) of its own: one in a dependency or a generated folder
    (`vendor/`, `testdata/`) is no test of the project. Rust keeps its unit tests beside the code, which no name shows, so a
    Rust repo counts by its `tests/` folder alone."""
    from .maintained import DEPENDENCY_DIRS, GENERATED_DIRS
    from .testrot import TEST_FILE

    named = git(["ls-files", "-z", "--", "*test*", "*Test*"], repo) or ""
    skipped = DEPENDENCY_DIRS | GENERATED_DIRS
    return any(TEST_FILE.search(name) and not skipped & set(name.split("/")[:-1]) for name in named.split("\0"))


def one_line(command: str) -> str:
    """The first line of a command, cut to MAX_SHOWN characters."""
    first = command.strip().splitlines()[0] if command.strip() else ""
    return first if len(first) <= MAX_SHOWN else first[:MAX_SHOWN] + "..."


def named(rels: List[str]) -> str:
    """The first MAX_NAMED of the paths `rels`, and how many more."""
    more = len(rels) - MAX_NAMED
    return ", ".join(rels[:MAX_NAMED]) + (f" and {more} more" if more > 0 else "")


def verdict(root: Path, files: List[Path], runs: List[dict]) -> Optional[Tuple[Path, str, str]]:
    """What the test `runs` show about the code `files` the turn changed in the work tree at `root`: the file the finding
    sits on, its rule and its message; None when every file has a passing run on its current content and the last run
    didn't fail.

    A file with no passing run on its content is untested (`tests_not_run`, naming up to MAX_NAMED of them, on the first in
    path order, so that its key is stable). When the last run by time failed, and tested every untested file there is,
    the finding is `tests_failed` instead: the tests ran and are what is wrong. A file changed since that run is
    untested content, and `tests_not_run` comes first."""
    from .testtree import coverage

    by_rel = dict(zip(rel_paths(root, files), files))
    current = worktree_blobs(root, list(by_rel.values()))
    if not current:
        return None  # git didn't say what the files hold: a check that can't tell blocks nothing
    seen = coverage(root, runs, current)
    passing = set().union(*(c for run, c in zip(runs, seen) if run["exit"] is None))
    missing = [rel for rel in sorted(by_rel) if rel not in passing]
    last = runs[-1] if runs else None
    if last and last["exit"] is not None and all(rel in seen[-1] for rel in missing):
        return by_rel[min(by_rel)], TESTS_FAILED, f"the last test run failed: {last['exit']}, `{one_line(last['cmd'])}`"
    if missing:
        return by_rel[missing[0]], TESTS_NOT_RUN, f"{NOT_RUN}: {named(missing)}"
    return None


def off_here(repo: Path) -> bool:
    """Whether the repo turned the rule off: `tests_not_run` among the `smells_off` of its .broom.json."""
    off = repo_config(repo).get("smells_off")
    return isinstance(off, list) and TESTS_NOT_RUN in off


def repo_finding(repo: Path, files: List[Path], rows: List[dict]) -> Optional[Issue]:
    """The finding for a repo whose code `files` the turn changed, or None."""
    if off_here(repo) or not tracks_tests(repo):
        return None
    found = verdict(repo, files, test_runs(rows, repo))
    return Issue(TESTS_TOOL, repo, found[0], 0, 0, found[1], found[2]) if found else None


def findings(d: Path, root: Optional[Path], files: List[Path]) -> List[Issue]:
    """The findings of a turn's end for the code `files` the turn in `d` changed: none for a subagent (`root` is None), for
    a repo that turned the rule off or tracks no test file, or where every file has a passing run on its content and the
    last run passed. A rule the turn accepted is left out for the rest of the turn."""
    if root is None:
        return []
    by_repo: Dict[Path, List[Path]] = {}
    for f in files:
        repo = git_root(f.parent)
        if repo:
            by_repo.setdefault(repo, []).append(f)
    rows, accepted = runs_of(d), {r.get("rule") for r in accepted_rows(d)}
    found = (repo_finding(repo, group, rows) for repo, group in by_repo.items())
    return [i for i in found if i is not None and i.rule not in accepted]
