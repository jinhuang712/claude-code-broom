# 006. A smell counts when the change pushed it past a limit, not whenever it grew

Decided: 2026-11-13

---

## The problem

Across six of the author's repos, 20 to 265 source files sit over 400 lines. A hint on every added line would have been the norm, and noise teaches Claude to override broom.

---

## The choice

A sized smell counts when the change pushed it past a limit, or grew it while past the hard one. Growth between the limits is left alone.

---

## Not chosen

- **Plain growth**: It is more literal and measured badly: a hint on every added line.

---

## Consequences

A function already past the hard limit blocks on every line it gains, and one between the limits can grow up to the hard limit without a word.
