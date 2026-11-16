# 003. A lint result passes on an unchanged retry, and a type error only fixed or accepted

Decided: 2026-11-13

---

## The problem

A linter can be wrong, and a finding can predate the change. Blocking the same result again traps Claude in a loop. But a retry alone let a subagent commit 167 tsc errors without a word.

---

## The choice

Committing the same lint result again passes and records it as known. A type or compile error passes fixed, or after `broom known --accept "<why>"`, which records the reason.

---

## Not chosen

- **Every finding passes on a retry**: That is how the 167 type errors went through.
- **Nothing passes on a retry**: A false positive would then cost a loop instead of one round.

---

## Consequences

A real lint finding can pass on a second try with no reason on record. In one migration, workers accepted their own blocks although their instructions said not to, so `BROOM_NO_ACCEPT` turns accepting off where agents must fix what they break. Stopping a turn twice records the rest as known and leaves type errors out, so the commit still stops on them.
