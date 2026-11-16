# 016. A smell past the hard limit blocks like a type error

Decided: 2026-11-13

---

## The problem

A hint can be left unfixed. Some sizes are past what a hint should carry.

---

## The choice

Past the hard limit a smell is severe: it blocks the commit, where a smell past the soft limit only hints there.

---

## Not chosen

- **Every smell is a hint**: A smell of any size could then be left unfixed.

---

## Consequences

Stopping a turn twice leaves severe smells out of the known record, so the commit still stops on them.
