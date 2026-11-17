# TODO

---

## ongoing

---

### [P2][IDEA] A hint at the edit for a signal that is cheap and certain

- description: A file that just passed 1,000 lines could be told at the edit, before more is written into it. PROPOSAL argues against a lint after every edit, and that argument is about half-finished code, which a line count is not.
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

- description: lizard measures function length, complexity, parameters and nesting in Go, TS/JS, Python, Rust and Swift. It could fill Rust's and Swift's gaps with one tool. Its parsers are partial, so it needs a run beside the current measurers first.
- created: 2026-11-17
- related: [F8.3: Rust](../features/F8-languages.md#f83-rust)

---

### [P2][IDEA] Broken links in docs

- description: A link checker such as lychee could tell when a doc points at a file that is gone.
- created: 2026-11-17

---

### [P2][IDEA] Dependencies that fell far behind

- description: A package many major versions behind is rot the unused-package tools don't see. Finding it asks a registry, so it would run only on request, like the vulnerability lookup.
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

- description: `any`, a forced cast and the like are hinted when a change adds one, and nothing counts them across the repo. A counter would tell when typing got looser over a month.
- created: 2026-11-17
- found: the look for missed rot at the end of CP5
- related: [F11.1: Counters](../features/F11-checkup.md#f111-counters)
