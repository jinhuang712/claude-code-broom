# 018. broom offers a cleanup and never starts one

Decided: 2026-11-13

---

## The problem

Smells already in a repo need someone to go after them, and the user won't remember to ask.

---

## The choice

When a scan finds smells past the hard limit, Claude is told to raise them at a natural point and offer a cleanup. "Not now" records the count, and the note returns only when it grows.

---

## Not chosen

- **Start the cleanup unasked**: The user decides what their repo's time goes to.

---

## Consequences

A repo whose severe count never grows is raised once and then stays quiet.
