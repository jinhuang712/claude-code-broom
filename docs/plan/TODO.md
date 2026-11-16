# TODO

---

## ongoing

---

### [P1][DISCUSSION] Who pushes and tags a release?

- description: The user gave the agent the details and kept the direction. Pushing and tagging publish a release to every user of the plugin, and the rule so far was that the user says when.
- created: 2026-11-17
- status: OPEN
- found: the docs pass
- blocks: CP1 in [ROADMAP.md](ROADMAP.md)
- next: ask the user

---

### [P1][DISCUSSION] How far does "clean as you go" reach?

- description: Today only what a change made worse counts, and old code left as it was never comes up. The wider reading is that a change also cleans an old smell in the code it touches. The wider reading gives up the promise that legacy code stays quiet.
- created: 2026-11-17
- status: OPEN
- found: the user's direction of 2026-11-17
- blocks: how [F4.1: Sized smells](../features/F4-smells.md#f41-sized-smells) treats a function past the hard limit that grows a line at a time
- next: ask the user

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
