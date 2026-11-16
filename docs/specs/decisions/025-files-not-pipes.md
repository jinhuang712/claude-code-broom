# 025. A command writes to files, not pipes

Decided: 2026-11-16

---

## The problem

A pipe stays open as long as any process holds its end. A tool that exited and left a daemon behind kept broom waiting for the daemon: 12.0 seconds for a tool that took no time, and with no limit after a timeout.

---

## The choice

A command's output goes to temporary files and is read when the command is done. A command reads no input.

---

## Not chosen

- **Read pipes with a timeout**: The wait after a kill still had no end.

---

## Consequences

Output is not seen while a command runs.
