"""What a hook that is still running after SLOW_AFTER seconds was doing, written to `hook-trace.log` in broom's data
directory: where each thread is, and what processes the hook has started and not heard from. A hook that ends in
time writes nothing. It answers what an end at Claude Code's timeout never does: whether broom, or a tool it
started, was the one holding things up, and in which call."""

from __future__ import annotations

import faulthandler
import os
import threading
import time
from typing import List

from .gitutil import run
from .state import DATA_ROOT

LOG = DATA_ROOT / "hook-trace.log"
SLOW_AFTER = 20  # seconds; a hook is cut off at 25 (gitutil.HOOK_SECONDS)
MAX_BYTES = 256 * 1024
PS_FIELDS = 4  # pid, ppid, etime and the command, which has spaces


def descendants(rows: List[str], root: int) -> List[str]:
    """The `ps -o pid,ppid,etime,command` rows of the processes started, however indirectly, by `root`."""
    parent = {}
    for row in rows:
        fields = row.split(None, PS_FIELDS - 1)
        if len(fields) == PS_FIELDS and fields[0].isdigit() and fields[1].isdigit():
            parent[int(fields[0])] = int(fields[1])
    family = {root}
    grew = True
    while grew:
        grew = False
        for pid, ppid in parent.items():
            if ppid in family and pid not in family:
                family.add(pid)
                grew = True
    return [row for row in rows if row.split(None, 1)[0].isdigit() and int(row.split(None, 1)[0]) in family - {root}]


def write(event: str, cwd: str, started: float) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > MAX_BYTES:
            LOG.write_text("")
        _, listing, _ = run(["ps", "-axo", "pid,ppid,etime,command"], cwd=LOG.parent, timeout=3)
        with open(LOG, "a") as f:
            f.write(f"\n== {time.strftime('%Y-%m-%d %H:%M:%S')} hook {event} (pid {os.getpid()}) still running after "
                    f"{time.monotonic() - started:.0f} s, in {cwd}\n")
            faulthandler.dump_traceback(file=f, all_threads=True)
            f.write("-- processes it started:\n")
            f.write("\n".join(descendants(listing.splitlines(), os.getpid())) or "(none)")
            f.write("\n")
    except OSError:
        pass  # a trace that can't be written must not be the thing that stops the hook


def watch(event: str, cwd: str) -> None:
    """Arm the trace for this hook run."""
    timer = threading.Timer(SLOW_AFTER, write, args=(event, cwd, time.monotonic()))
    timer.daemon = True
    timer.start()
