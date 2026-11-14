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
from typing import Dict, List, Optional

from .common import git, git_changed_files, lang_of, load_json, save_json, session_dir
from .maintained import DEPENDENCY_DIRS

SNAPSHOT = "snapshot.json"  # {repo: {"head": sha, "files": {path: [mtime_ns, size]}}}
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


def code_changes(root: Path) -> Dict[str, List[int]]:
    """The repo's changed and untracked code files outside dependencies, with their modification time and size:
    cheap enough for every prompt, unlike reading them."""
    out = {}
    for f in git_changed_files(root):
        rel = f.relative_to(root).as_posix()
        if lang_of(f) and not DEPENDENCY_DIRS & set(rel.split("/")[:-1]):
            st = f.stat()
            out[rel] = [st.st_mtime_ns, st.st_size]
    return out


def snapshot(d: Path, root: Path) -> None:
    data = load_json(d / SNAPSHOT, {})
    data[str(root)] = {"head": (git(["rev-parse", "HEAD"], root) or "").strip(), "files": code_changes(root)}
    save_json(d / SNAPSHOT, data)


def changed_since_snapshot(d: Path, root: Path) -> List[Path]:
    """Code files changed since the snapshot by any means, and those committed since, as they are now."""
    snap = load_json(d / SNAPSHOT, {}).get(str(root))
    if not snap:
        return []
    out = [root / rel for rel, stat in code_changes(root).items() if snap["files"].get(rel) != stat]
    head = (git(["rev-parse", "HEAD"], root) or "").strip()
    if snap.get("head") and head and head != snap["head"]:
        committed = git(["diff", "--name-only", "--diff-filter=ACMR", snap["head"], head], root) or ""
        out += [root / n for n in committed.splitlines() if n and lang_of(root / n)]
    return [f for f in dict.fromkeys(out) if f.is_file()]


def turn_base(d: Path, root: Optional[Path]) -> str:
    """What the turn's changes are measured against: HEAD as the prompt found it, so a commit made during the turn
    still shows as the turn's change. HEAD itself without such a note, or once that commit is gone."""
    head = (load_json(d / SNAPSHOT, {}).get(str(root)) or {}).get("head") if root else None
    if head and git(["rev-parse", "--verify", "-q", f"{head}^{{commit}}"], root) is not None:
        return head
    return "HEAD"


def waiting(d: Path) -> bool:
    """Whether the gate is waiting for background work, from an earlier turn's end."""
    return (d / DEFERRED).exists()


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
