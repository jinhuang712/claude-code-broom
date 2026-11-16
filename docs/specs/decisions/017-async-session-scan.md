# 017. The session scan runs in an async hook

Decided: 2026-11-15

---

## The problem

Claude's first reply waits for session-start hooks. On a 2,376-file repo the scan took 13 to 36 seconds and passed the hook's 30-second timeout once in six runs, which threw the result away and left nothing cached.

---

## The choice

The scan runs in an async hook when HEAD has no cached scan. The session hook says only what a cached scan knows.

---

## Not chosen

- **Scan inside the session hook**: The first reply waited, and a timeout lost the result.

---

## Consequences

The note from a fresh scan reaches Claude with its next turn, not its first.
