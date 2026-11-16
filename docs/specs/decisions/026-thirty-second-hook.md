# 026. A hook run is cut at 30 seconds instead of waiting for its tools

Decided: 2026-11-16

---

## The problem

The commit and stop hooks had a 300-second timeout and the async ones none. A slow tool made the session feel stuck, and a linter's compiler kept running after it.

---

## The choice

Every hook has a 30-second timeout. The commands a run starts share 25 seconds, and one that runs out is killed with everything it started. At 28 seconds the hook gives up and lets the commit, the edit or the stop through.

---

## Not chosen

- **Wait for the tools**: A hook could hold the session for up to 300 seconds.

---

## Consequences

This is a limit and not a speed-up: a tool takes as long as it did. A cold `cargo clippy` or `swift build` can be cut off, and that check is then skipped for 20 minutes.
