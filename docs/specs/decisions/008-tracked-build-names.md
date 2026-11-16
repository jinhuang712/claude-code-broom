# 008. Directories named like build output are skipped only where git doesn't track them

Decided: 2026-11-14

---

## The problem

Skipping by directory name keeps dependencies out without reading them, but a name is a guess. `release` held a family of hand-written adapters in one repo. Their smells went unreported, and five files only that directory imported were called dead.

---

## The choice

`build`, `out`, `release` and `target` count as build output only where git doesn't track the files. Tracked directories still skipped by name are listed in a note.

---

## Not chosen

- **Skip those names everywhere**: Hand-written code under them went unread.
- **Skip nothing by name**: An unignored and untracked `node_modules` and app build once put 58,000 files in a sweep's scope.

---

## Consequences

A repo that tracks its build output gets that output measured.
