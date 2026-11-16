# 005. Smells are measured by broom's limits in a scratch copy, not by the project's lint config

Decided: 2026-11-13

---

## The problem

How long a function may grow is the user's bar, not each repo's. A project's lint config would move that bar from one repo to the next.

---

## The choice

Each tool runs alone in a scratch copy of the changed files under a config broom writes, once as the files are and once at the base revision.

---

## Not chosen

- **The project's own lint config**: The bar would differ per repo.

---

## Consequences

The same tool can run twice on a file, once for lint and once for smells. The scratch copy holds the changed files and not their packages, so imports don't resolve there. `.broom.json` `limits` moves the bar per repo.
