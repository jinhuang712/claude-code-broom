# 011. Code marked legacy may be repeated by new code

Decided: 2026-11-15

---

## The problem

A migration writes the new code beside the old before deleting it. Every step of one repeated code the repo was about to drop.

---

## The choice

`.broom.json` `legacy` names code on its way out, and clones with a side in it don't count.

---

## Not chosen

- **Count them as duplicates**: Every step of the migration repeated code the repo was about to drop.

---

## Consequences

Someone has to list the legacy paths and remove them when the migration ends.
