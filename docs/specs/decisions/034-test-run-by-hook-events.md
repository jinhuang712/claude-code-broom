# 034. A test run is known by the hook events of its command, and its accept holds for one turn

Decided: 2026-11-18

---

## The problem

A turn that changed code and ran no test has work left over, and broom runs no test itself. It needs a trace of a test run that Claude can't make up in words.

---

## The choice

Claude Code says what became of a Bash command by the event it fires: one after a command that exited 0, another after one that didn't. broom already sees each command before it runs. So a command that is a test run is noted when it starts, and a new hook on the failure event notes one that failed. A test run that started and has no failure after it counts as passed.

An accept of this finding holds for its turn only. It is written to the record, and it never becomes a known issue.

---

## Not chosen

- **A coverage report newer than the change**: Only a project that writes one would have a trace.
- **The files a test runner leaves**: They differ by runner, and an old one would vouch for a new change.
- **A hook after every Bash call**: Each call would pay one more process to learn what the failure event already tells.
- **An accept that holds for 30 days**: One accept would turn the rule off for a month.

---

## Consequences

A test command is known by its words, from a list of runners and what a repo names in `test_commands`, so a runner of a project's own can go unseen until it is named. A test run in the background or piped into another command exits 0 as far as the hook can tell, so it counts as passed.
