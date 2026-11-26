"""What a turn changed, and whether its end is the end.

Edits through Edit and Write are recorded as they happen, per agent: a subagent's go to its own record, so its own
end (SubagentStop) checks them and it fixes them itself, not the session that started it. What a Bash command
changes (sed, a codemod, a script, `git mv`) leaves no record, and a wrapper that commits leaves no `git commit` to
see: the prompt hook notes the working tree's changed code files and HEAD, and the turn's end adds whatever changed
or was committed since.

A turn that ends while background work runs (a test run, a build, a subagent) is a pause, not the end: the gate
waits for a turn the work wakes, up to half an hour, so a server left running in the background doesn't keep it
waiting forever.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional

from .config import REPO_FILE
from .gitutil import git, git_root, tree_state
from .maintained import DEPENDENCY_DIRS
from .state import load_json, save_json, session_dir
from .toolchain import lang_of

SNAPSHOT = "snapshot.json"  # {repo: {"head": sha, "files": {path: [mtime_ns, size]}, "t": second it was noted}}
DEFERRED = "deferred.json"  # {"t": when the gate first waited for background work}
WAIT_SECONDS = 1800
FINISHED = {"completed", "failed", "killed", "stopped", "cancelled", "canceled", "done", "error", "timeout"}


def turn_dir(data: dict) -> Path:
    """Where a turn's records live: the session's directory, or for a subagent's hook, the subagent's own."""
    sd = session_dir(data.get("session_id") or "cli")
    agent = data.get("agent_id")
    if not agent:
        return sd
    d = sd / "agents" / re.sub(r"[^A-Za-z0-9_.-]", "_", str(agent))
    d.mkdir(parents=True, exist_ok=True)
    return d


def tree(root: Path) -> dict:
    """The repo's HEAD and its changed and untracked code files outside dependencies, each with its modification time
    and size: one git call and no file read, cheap enough for every prompt and every turn's end. The repo's own
    .broom.json is among them: a turn that loosens it by any means is seen."""
    head, changed = tree_state(root)
    files = {}
    for f in changed:
        rel = f.relative_to(root).as_posix()
        if rel == REPO_FILE or (lang_of(f) and not DEPENDENCY_DIRS & set(rel.split("/")[:-1])):
            st = f.stat()
            files[rel] = [st.st_mtime_ns, st.st_size]
    return {"head": head, "files": files}


def snapshot(d: Path, root: Path, now: Optional[dict] = None) -> None:
    """Record the repo's tree (`now`, or as it is read here) and the second it was read in the turn's snapshot in `d`,
    to compare at the turn's end."""
    data = load_json(d / SNAPSHOT, {})
    data[str(root)] = {**(now or tree(root)), "t": int(time.time())}
    save_json(d / SNAPSHOT, data)


def committed_in_turn(root: Path, snap: dict, head: str) -> List[str]:
    """The files that commits made since the snapshot added or changed. A commit the turn brought in, by a pull, a
    reset to another branch or a landing of work done before the prompt, was committed before the snapshot and is
    not the turn's; a merge counts only what it resolved. A snapshot with no time counts every commit."""
    out = git(["log", "--format=%x00%ct", "--name-only", "--diff-filter=ACMR", "-c", f"{snap['head']}..{head}"], root)
    files: List[str] = []
    for chunk in (out or "").split("\0")[1:]:
        when, _, names = chunk.partition("\n")
        if when.isdigit() and int(when) >= snap.get("t", 0):
            files += [n for n in names.splitlines() if n]
    return files


def changed_since_snapshot(d: Path, root: Path, now: dict) -> List[Path]:
    """Code files, and the repo's .broom.json, changed since the snapshot by any means, and those committed since,
    as they are in the tree `now`."""
    snap = load_json(d / SNAPSHOT, {}).get(str(root))
    if not snap:
        return []
    out = [root / rel for rel, stat in now["files"].items() if snap["files"].get(rel) != stat]
    if snap.get("head") and now["head"] and now["head"] != snap["head"]:
        committed = committed_in_turn(root, snap, now["head"])
        out += [root / n for n in committed if n == REPO_FILE or lang_of(root / n)]
    return [f for f in dict.fromkeys(out) if f.is_file()]


def turn_base(d: Path, root: Optional[Path]) -> str:
    """What the turn's changes are measured against: HEAD as the prompt found it, so a commit made during the turn
    still shows as the turn's change. When the turn brought in commits made before the prompt, the newest of them on
    HEAD's line, so what they hold is not the turn's. HEAD itself without a note, or once that commit is gone."""
    if root is None:
        return "HEAD"
    snap = load_json(d / SNAPSHOT, {}).get(str(root)) or {}
    head = snap.get("head")
    if not head or git(["rev-parse", "--verify", "-q", f"{head}^{{commit}}"], root) is None:
        return "HEAD"
    line = git(["log", "--first-parent", "--format=%H %ct", f"{head}..HEAD"], root) or ""
    older = [sha for sha, _, when in (c.partition(" ") for c in line.splitlines()) if int(when) < snap.get("t", 0)]
    return older[0] if older else head


def note_config(path: Path, sd: Path) -> None:
    """A repo's own .broom.json, at `path`, was changed in the turn whose records are in `sd`: note now what it
    loosens against the turn's base. A `check_on` set to off, which no later check would see, is on record this way
    too. What reads a config's waivers loads the smells with it, so it is loaded here, when a config changed."""
    from . import ledger, waivers

    root = git_root(path.parent)
    if root and path == root / REPO_FILE:
        ledger.waived(waivers.config_waivers(root, turn_base(sd, root)), sd)


def waiting(d: Path) -> bool:
    """Whether the gate is waiting for background work, from an earlier turn's end, for half an hour at most."""
    first = load_json(d / DEFERRED, {}).get("t")
    return first is not None and time.time() - first < WAIT_SECONDS


def paused(data: dict, d: Path) -> bool:
    """Whether this turn ended while background work runs, so the gate waits; for half an hour at most."""
    live = [t for t in data.get("background_tasks") or []
            if isinstance(t, dict) and str(t.get("status", "")).lower() not in FINISHED]
    if not live:
        return False
    first = load_json(d / DEFERRED, {}).get("t")
    if first is None:
        save_json(d / DEFERRED, {"t": time.time()})
        return True
    return time.time() - first < WAIT_SECONDS
