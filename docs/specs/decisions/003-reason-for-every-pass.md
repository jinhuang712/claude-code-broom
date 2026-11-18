# 003. Every finding passes fixed, or accepted with a reason

Decided: 2026-11-17

---

## The problem

A linter can be wrong, and a finding can predate the change, so a block needs a way out. The way out used to be to run the same commit again, or to stop again. It left no reason: over 30 days one machine let hundreds of findings through that way, and nobody could say which of them were wrong and which were skipped.

---

## The choice

A blocking finding passes fixed, or after `broom known --accept "<why>"`, which records it as known with the reason.

---

## Not chosen

- **A lint result passes on an unchanged retry**: It costs nothing and leaves no reason. Before type errors were taken out of it, a subagent committed 167 tsc errors by running the same commit twice.
- **Nothing passes without a fix**: A false positive would then trap Claude in a loop.

---

## Consequences

A false positive costs one command and one sentence. `BROOM_NO_ACCEPT` turns accepting off where agents must fix what they break, as in one migration workers accepted their own blocks against their instructions.
