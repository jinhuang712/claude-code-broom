# 019. The turn-end check waits while background work runs

Decided: 2026-11-15

---

## The problem

A turn that ends while a test suite or a build runs in the background is a pause. Blocking it there, for a hint, once made Claude change files under a running test suite, which then had to run again.

---

## The choice

The check waits while any background task runs and checks at the turn that work wakes.

---

## Not chosen

- **Check at every stop**: It changed files under a running test suite.

---

## Consequences

Each task is waited for once, by its id, since a server left running would keep the check waiting forever. Until 0.29.0 the wait was given up after half an hour; [048: No rule turns on the clock](048-no-clock.md) replaced that.
