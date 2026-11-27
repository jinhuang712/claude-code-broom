# TODO

---

## ongoing

---

### [P1][DISCUSSION] What it takes for a second user to install broom and stay

- description:
  - Every number in the ledger and every end-to-end run comes from the author's machine. The repo had no star, no fork and no issue on 2026-11-20.
  - The user set the order that day: broom gets lighter first, then it finds a second user.
  - 3 points are open: which systems count while Linux and Windows are unsupported · where broom is announced · what "stay" means and how it is checked.
- created: 2026-11-20
- status: HALT
- found: the user, in the session of 2026-11-20
- blocks: the checkpoint that follows CP13
- next: settle the 3 points with the user once CP8 has its numbers

---

### [P2][DISCUSSION] Whether the limits come down now that a length counts code lines

- description:
  - Since 2026-11-24 a length leaves out comment lines and blank lines, and the limits stayed at 50 and 100 for a function and 400 and 1000 for a file.
  - Every length reads smaller, so the bar is looser by as much as a file holds comments and blank lines. broom's own `lib/` holds 9,227 code lines in 13,950 lines.
  - The user set that day that the limits are a decision of their own.
  - A test file's limits are twice the code's since that day, and since 2026-11-27 a test file past them is a nit, so they only decide when a test's length is told.
- created: 2026-11-24
- status: OPEN
- found: the user's change of 2026-11-24
- related: [039: A length counts code lines](../specs/decisions/039-code-lines.md)
- next: decide with the user, with the ledger's numbers for the length smells

---

### [P2][IDEA] Test helpers in the other languages

- description:
  - Since 2026-11-27 a Go test-helper package, a folder whose name ends in `test`, and pytest's `conftest.py` are test code.
  - Since that day TS/JS's `__mocks__/` and setup files are test code too. The others keep helpers by habit and not by a rule: TS/JS's `test-utils`, Swift's `TestSupport` targets, Rust's helper crates.
  - A Go package of fakes that only tests import, such as `fakeclock`, is code too. Telling it needs the module's import graph.
- created: 2026-11-27
- found: the change to Go's test-helper packages
- related: [045: A Go test-helper package is test code](../specs/decisions/045-test-helper-packages.md)

---

### [P2][IDEA] The doctor offers ast-grep in a CSS repo

- description: CSS's comments are read by ast-grep, for its file length and its counters. `broom doctor` offers ast-grep only in a repo with Go, Rust or TS/JS, so a repo of CSS alone gets the note that it is missing and no offer.
- created: 2026-11-24
- found: the change to code lines
- related: [F1.1: Doctor](../features/F1-setup.md#f11-doctor)

---

### [P2][IDEA] INSTALL says what to do when an install fails

- description:
  - INSTALL has no part for a failed install, and nobody has recorded what one shows.
  - Every install so far ran on the author's machine, so the first install by a stranger is where the cases come from.
- created: 2026-11-20
- found: the docs pass of 2026-11-20
- related: [What it takes for a second user to install broom and stay](#p1discussion-what-it-takes-for-a-second-user-to-install-broom-and-stay)

---

### [P2][IDEA] A hint at the edit for a signal that is cheap and certain

- description:
  - A file that just passed 1,000 lines could be told at the edit, before more is written into it.
  - The check after an edit tells what a fast linter finds, and a size is not among it.
  - A line count is cheap and certain, so it fits that moment.
- created: 2026-11-17
- next: decide with the ledger's numbers

---

### [P2][IDEA] Declared layers per project

- description: Tools such as import-linter and dependency-cruiser hold imports to layers a project wrote down. broom reports cycles, which need no rules. Layers would need the user to write them.
- created: 2026-11-17
- related: [014: No layering rules without a project's own](../specs/decisions/014-no-layering-rules.md)

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

---

### [P2][IDEA] broom says which smells a repo's languages lack

- description:
  - The user asked on 2026-11-19 how many smells each language measures, and the answer came from reading the code.
  - `broom doctor --checks` lists the checks that run. It could list, per language of the repo, the smells that language doesn't measure.
- created: 2026-11-19
- found: the user's question
- related: [F1.5: Protection list](../features/F1-setup.md#f15-protection-list)

---

### [P2][IDEA] Tests that no runner collects

- description:
  - A test file outside every pattern the project's runner collects, a Rust test behind a feature that no build turns on, or a Swift test outside any test target, passes by never running.
  - broom counts it as a test and pairs code with it, so the code reads as tested.
  - Telling it needs each runner's own config: pytest's `testpaths`, a Jest or Vitest `include`, Cargo's features and SwiftPM's targets.
- created: 2026-11-20
- found: the look for missed rot at the end of CP10
- related: [F4.2.3: Untested file](../features/F4-smells.md#f423-untested-file)

---

### [P2][IDEA] Counts in docs that drift from the code

- description:
  - A doc or an image that says how many things the code has goes stale when one is added, and no change to that doc is at fault.
  - The README's hero lists the 27 smells by name, and the docs say how many checks `broom doctor` runs and how many smells each language measures.
  - A counter could compare such a number with the code's own list, where a project names that list.
- created: 2026-11-20
- found: the look for missed rot at the end of CP9
- related: [F11.1: Counters](../features/F11-checkup.md#f111-counters)

---

### [P2][IDEA] A Go error dropped from a call that does work

- description:
  - 0.30.1 counted every Go error dropped with `_` as a `swallowed_error` nit, and 0.30.2 took it back out: in a real Go repo most of what it flagged was cleanup or an encode, the form errcheck itself asks for.
  - What is left worth a reader is a dropped error of a call that does work, such as a write to a store or a run of a job, above all in a test that drops the error of the call it tests.
  - Telling it apart needs the call's kind from the tree or from types. A list of names such as `Close` would be a guess.
- created: 2026-11-27
- found: a real Go repo's report on 0.30.1
- related: [050: More rot is counted, each from what parses it](../specs/decisions/050-rot-read-from-trees.md)

---

### [P2][IDEA] A rule new in a version is named where it moves a count

- description:
  - A new rule in a release can move a repo's total at once: one new nit rule took a repo near zero to hundreds of smells, and nothing said that the code was the same.
  - The first scan after an upgrade could name each rule that is new in this version of broom beside the count it added.
  - broom's version is in each record since 0.29.0, so the event is the first scan on a new version, not a day.
- created: 2026-11-27
- found: a real Go repo's report on 0.30.1
- related: [F10.1: Whole-repo diagnosis](../features/F10-diagnosis.md#f101-whole-repo-diagnosis)
