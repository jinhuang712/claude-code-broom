# TODO

---

## ongoing

---

### [P1][DISCUSSION] A hero image for the README

- description: The README opens with no image. Which image stands for broom is the user's pick, from options shown side by side.
- created: 2026-11-18
- status: OPEN
- found: the docs pass of 2026-11-18
- blocks: [I1: The moved text doesn't meet the wording rules](ISSUES.md#i1-the-moved-text-doesnt-meet-the-wording-rules)
- next: draw a few options and show them on one sheet

---

### [P2][DISCUSSION] Where a contributor asks first

- description: CONTRIBUTING states the bar for a change and names no place to ask before starting one.
- created: 2026-11-18
- status: OPEN
- found: the docs pass of 2026-11-18
- next: the user names the place, such as the repo's GitHub issues

---

### [P2][DISCUSSION] One open way to ask broom, in place of a flag per question

- description:
  - The user asked on 2026-11-18 for two things: a scope, excludes and limits that a call can set, and a way to ask broom anything, as Code Mode lets a model write code against an API.
  - The forms on the table: more flags · a full export of the measurements for a script outside broom · SQL over a database broom fills · one JSON query · a script that broom runs · a library to import.
  - The want "no script to write" and its goal say a session writes no script, which several of these forms reverse.
  - The user narrowed it that day: the ability sits inside broom, so that the command line needn't cover every case. An export for a script outside broom and a library are out.
  - The user rejected SQL over a database that day.
- created: 2026-11-18
- updated: 2026-11-18
- status: OPEN
- found: the user, in the session of 2026-11-18
- next: say again what broom is and whom it serves, then judge the forms from there

---

### [P2][IDEA] A hint at the edit for a signal that is cheap and certain

- description:
  - A file that just passed 1,000 lines could be told at the edit, before more is written into it.
  - PROPOSAL argues against a lint after every edit.
  - That argument is about half-finished code, which a line count is not.
- created: 2026-11-17
- next: decide with the ledger's numbers

---

### [P2][IDEA] A model reviews what no tool can measure

- description: Naming and misplaced responsibility need judgment. A review by a model costs tokens at every turn and gives a different answer twice, so it waits until the measured checks are done.
- created: 2026-11-17

---

### [P2][IDEA] Declared layers per project

- description: Tools such as import-linter and dependency-cruiser hold imports to layers a project wrote down. broom reports cycles, which need no rules. Layers would need the user to write them.
- created: 2026-11-17
- related: [014: No layering rules without a project's own](../specs/decisions/014-no-layering-rules.md)

---

### [P2][IDEA] One measurer for sized smells in every language

- description:
  - lizard measures 4 sizes: function length · complexity · parameters · nesting.
  - It covers 5 languages: Go · TS/JS · Python · Rust · Swift.
  - It could fill Rust's and Swift's gaps with one tool.
  - Its parsers are partial, so it needs a run beside the current measurers first.
- created: 2026-11-17
- related: [F8.3: Rust](../features/F8-languages.md#f83-rust)

---

### [P2][IDEA] Broken links in docs

- description: A link checker such as lychee could tell when a doc points at a file that is gone.
- created: 2026-11-17

---

### [P2][IDEA] Dependencies that fell far behind

- description:
  - A package many major versions behind is rot the unused-package tools don't see.
  - Finding it asks a registry, so it would run only on request like the vulnerability lookup.
- created: 2026-11-17
- found: the look for missed rot at the end of CP5
- related: [030: Known vulnerabilities are looked up only on request](../specs/decisions/030-vulnerabilities-on-request.md)

---

### [P2][IDEA] Tests that assert nothing

- description: A test with no assertion passes whatever the code does. Finding one needs each language's test forms, and a helper that asserts for the test would read as a miss.
- created: 2026-11-17
- found: the look for missed rot at the end of CP5

---

### [P2][IDEA] Rules turned off in the project's lint config

- description: A lint config loses rules one at a time, and no change is at fault. A counter of the rules a config turns off would tell when it grew. Each linter writes that differently.
- created: 2026-11-17
- found: the look for missed rot at the end of CP5
- related: [F11.1: Counters](../features/F11-checkup.md#f111-counters)

---

### [P2][IDEA] The largest tracked files

- description: A binary or a data file committed by mistake stays in the repo for good. `broom stats` could list the largest tracked files beside the longest code files.
- created: 2026-11-17
- found: the look for missed rot at the end of CP5
- related: [F10.4: Numbers on request](../features/F10-diagnosis.md#f104-numbers-on-request)

---

### [P2][IDEA] Type escapes as a counter

- description:
  - A type escape such as `any` or a forced cast is hinted when a change adds one, and nothing counts them across the repo.
  - A counter would tell when typing got looser over a month.
- created: 2026-11-17
- found: the look for missed rot at the end of CP5
- related: [F11.1: Counters](../features/F11-checkup.md#f111-counters)

---

### [P2][IDEA] Doc comments that say nothing

- description: A doc comment copied onto many functions meets the rule and tells the reader nothing. A fresh session found one sentence on six functions of a test repo, where broom counted no missing comment. The same text on several functions of a repo could be counted.
- created: 2026-11-17
- found: the look for missed rot at the end of CP4
- related: [F11.5: Missing comments](../features/F11-checkup.md#f115-missing-comments)

---

### [P2][IDEA] A Python type check in the sweep

- description: Python has no type check at a commit or a turn's end, so a type error reaches Claude only through pyright as it edits. A project that configures mypy or pyright already says which checker it wants. Either would add seconds to each check.
- created: 2026-11-18
- found: a fresh session's commit on a public Python project that configures both, where the commit check ran ruff alone
- related: [F8.4: Python](../features/F8-languages.md#f84-python)

