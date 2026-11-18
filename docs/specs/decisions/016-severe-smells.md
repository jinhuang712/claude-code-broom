# 016. A smell past the hard limit blocks like a type error

Decided: 2026-11-13

---

## The problem

A hint can be left unfixed. Some sizes are past what a hint should carry.

---

## The choice

Past the hard limit a smell is severe: it blocks the commit like a type error, and one that was there and grew can't be accepted.

---

## Not chosen

- **Every smell is a hint**: A smell of any size could then be left unfixed.

---

## Consequences

A turn's end that gives up leaves severe smells out of the known record, so the commit still stops on them.
