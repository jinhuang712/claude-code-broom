# 007. A renamed file is measured against its old path, and import-only growth doesn't count

Decided: 2026-11-14

---

## The problem

"Made worse" needs the same file on both sides. Read at its new path, a moved file over the hard limit was new and blocked, as a refactor that moved modules into a new layout found on every move. Rewiring imports after a move, which a formatter then wraps, lengthened files already past the limit by a line or two and blocked commits that changed no logic.

---

## The choice

A file git sees as renamed is read at its old path, and its changed lines come from a rename-aware diff. A long file whose lines besides imports didn't grow isn't counted as longer.

---

## Not chosen

- **Treat a moved file as new**: Every move of a long file blocked.

---

## Consequences

A move must be one git sees as a rename: `git mv`, or a move staged with `git add`.
