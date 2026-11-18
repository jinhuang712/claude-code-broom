# 031. Trying again passes nothing, and three blocks end in a loud give-up

Decided: 2026-11-18

---

## The problem

A turn's end blocked once, and stopping again ended the turn with the finding open. A hint at a commit only told. Both let Claude carry on without a fix and without a reason, so an agent after speed could run to the end, and the user learned what it left only by asking.

---

## The choice

A finding that is more than slight passes only fixed or accepted with a reason. A hint blocks a commit. A turn's end blocks again until what is left is fixed or accepted. After three blocks broom lets go, and tells the user what is still open in words that can't be missed.

---

## Not chosen

- **Stopping again ends the turn**: It leaves no reason, and it is the cheapest way out, so it is the one taken.
- **A turn's end blocks with no limit**: Where accepting is turned off, or a finding can't be accepted, Claude would have no way out, and Claude Code would cut the session off with nothing told.
- **A hint only tells at a commit**: What a commit lets in needs one more commit to clean.

---

## Consequences

A task takes more rounds. A finding that is slight must be told apart from one that is not, since only the first may pass untold.
