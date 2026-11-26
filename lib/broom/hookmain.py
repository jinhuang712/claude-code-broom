"""`broom hook <event>`: what Claude Code's hooks and git's pre-commit hook call.

bin/broom comes here first. A hook runs without loading the command line (cli), and each event loads only its own
handler: an edit or a turn's end with nothing to do must cost little more than the start of Python.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, List

from . import ledger
from .gitutil import CLOCK, HOOK_SECONDS
from .hooktrace import watch
from .state import read_hook_input, warn

EVENTS = ("commit", "pre-commit", "edit", "prompt", "answer", "stop", "subagent-stop", "session", "session-scan",
          "test-failed")


def give_up_after(seconds: float, event: str) -> None:
    """The last resort for what no command's timeout reaches (broom's own reading of files on a huge repo): end
    the hook without a verdict, which lets the commit, the edit or the stop through, before Claude Code does."""
    def give_up() -> None:
        warn(f"broom hook {event}: gave up after {seconds:.0f} s")
        os._exit(0)

    timer = threading.Timer(seconds, give_up)
    timer.daemon = True
    timer.start()


def handler(event: str) -> Callable[[dict], None]:
    """What handles `event`, one of EVENTS but pre-commit, from the module that holds it."""
    if event == "edit":
        from .edithook import hook_edit
        return hook_edit
    if event in ("stop", "subagent-stop", "prompt"):
        from .turnhooks import hook_prompt, hook_stop
        return hook_prompt if event == "prompt" else hook_stop
    if event == "commit":  # PreToolUse on Bash: it notes a test run, and checks a commit when the command may hold one
        from .testrun import hook_pre_bash
        return hook_pre_bash
    if event == "answer":  # UserPromptSubmit, synchronous, only while a question waits (hooks/prompt.sh)
        from .comeback import hook_answer
        return hook_answer
    if event == "test-failed":  # PostToolUseFailure on Bash
        from .testrun import hook_failed
        return hook_failed
    from .sessionhooks import hook_session, hook_session_scan
    return hook_session if event == "session" else hook_session_scan


def pre_commit() -> int:
    """git's pre-commit hook: 1 when the commit is blocked. A broken check never stops a commit."""
    from .commitgate import hook_pre_commit

    try:
        return hook_pre_commit()
    except Exception as e:  # noqa: BLE001 - a broken check must never stop a commit
        warn(f"broom pre-commit: {e}")
        ledger.errored(e)
        return 0


def run_hook(event: str) -> int:
    """Run the check for `broom hook <event>`; an error is warned and let through, so 0 unless pre-commit blocks."""
    seconds = float(os.environ.get("BROOM_HOOK_SECONDS") or HOOK_SECONDS)  # the variable is for tests
    CLOCK.start(seconds)
    give_up_after(seconds + 3, event)
    watch(event, os.getcwd())
    ledger.begin(event)
    if event == "pre-commit":
        return pre_commit()
    data = read_hook_input()
    try:
        handler(event)(data)
    except Exception as e:  # noqa: BLE001 - a broken check must never trap Claude or block its edits
        warn(f"broom hook {event}: {e}")
        ledger.errored(e)
    return 0


def main(argv: List[str]) -> int:
    """Run `broom <argv>`: a hook from here, anything else through the command line, which is loaded only then."""
    command, events = argv[:1], argv[1:]
    if command == ["hook"] and len(events) == 1 and events[0] in EVENTS:
        return run_hook(events[0])
    from .cli import main as command_line

    return command_line(argv)
