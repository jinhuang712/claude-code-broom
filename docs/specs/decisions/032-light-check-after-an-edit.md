# 032. After an edit broom formats and runs what is judged in milliseconds

Decided: 2026-11-18

---

## The problem

Nothing ran after an edit by default, so Claude heard of a lint finding only at the commit, many edits later. A lint after every edit had been ruled out as slow and noisy: a warning in the middle of a change makes Claude fix what the next edit would have settled.

---

## The choice

After each edit broom formats the file and runs the checks that take milliseconds on one file. It tells Claude what it found and never blocks.

---

## Not chosen

- **Nothing after an edit**: The feedback comes late, and a formatter's rewrite lands at the commit.
- **The whole check after an edit**: A tool that needs a build takes seconds, and every edit would pay for it.
- **A block after an edit**: The edit has happened, and half-finished code is no finding yet.

---

## Consequences

A finding told after an edit can be gone by the next one. What is still there comes due at the commit.
