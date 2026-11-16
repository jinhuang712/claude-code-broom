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

The wait is given up after half an hour, as a server left running would keep it waiting forever.
