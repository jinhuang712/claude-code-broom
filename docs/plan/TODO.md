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
- blocks: the checkpoint that follows CP8
- next: settle the 3 points with the user once CP8 has its numbers

---

### [P2][DISCUSSION] Whether the limits come down now that a length counts code lines

- description:
  - Since 2026-11-24 a length leaves out comment lines and blank lines, and the limits stayed at 50 and 100 for a function and 400 and 1000 for a file.
  - Every length reads smaller, so the bar is looser by as much as a file holds comments and blank lines. broom's own `lib/` holds 9,227 code lines in 13,950 lines.
  - The user set that day that the limits are a decision of their own.
  - A test file's limits are twice the code's since that day, so they move with whatever is decided here.
- created: 2026-11-24
- status: OPEN
- found: the user's change of 2026-11-24
- related: [039: A length counts code lines](../specs/decisions/039-code-lines.md)
- next: decide with the user, with the ledger's numbers for the length smells

---

### [P2][IDEA] A test file's length that leaves its cases out

- description:
  - A test file may be twice as long as a code file, whatever it holds. A file of helper code among the tests gets that too, though helper code is code.
  - A test file's length could count only the code lines outside its test functions. The cases would then be free, and the helpers held to the code's limit.
  - broom already reads each language's test forms for the skipped tests and the test cases of `broom stats`.
- created: 2026-11-24
- found: the look at one repo's long test files
- related: [040: A test file may be twice as long as a code file](../specs/decisions/040-test-file-length.md)

---

### [P2][IDEA] A test class as a list of cases

- description: A test class lists cases as a test file does, and `type_lines` holds it to the code's 250. broom's own test classes stay within it, and no other repo was measured for it, so the limit stayed.
- created: 2026-11-24
- found: the change to a test file's limits
- related: [F4.7: Tests](../features/F4-smells.md#f47-tests)

---

### [P2][IDEA] A test file's length beside its code file's

- description:
  - The factor of 2 came from two throwaway scripts: one counted the test files past each limit, the other set each long test file beside the code file it is named for.
  - `broom stats` pairs code with tests by name already. Its test section could give each long test file's code lines, the share inside test functions and the code file's length.
- created: 2026-11-24
- found: the change to a test file's limits
- related: [F10.4: Numbers on request](../features/F10-diagnosis.md#f104-numbers-on-request)

---

### [P2][IDEA] A repeated block counted in code lines

- description: `duplicate_lines` is the one sized smell that still counts comment lines and blank lines, since jscpd counts a clone's lines its own way. The lines of each clone could be counted in code lines, as a length is.
- created: 2026-11-24
- found: the change to code lines
- related: [F4.3: Duplicate code](../features/F4-smells.md#f43-duplicate-code)

---

### [P2][IDEA] The doctor offers ast-grep in a CSS repo

- description: CSS's comments are read by ast-grep, for its file length and its counters. `broom doctor` offers ast-grep only in a repo with Go, Rust or TS/JS, so a repo of CSS alone gets the note that it is missing and no offer.
- created: 2026-11-24
- found: the change to code lines
- related: [F1.1: Doctor](../features/F1-setup.md#f11-doctor)

---

### [P2][IDEA] The lines a Swift or a Rust function takes

- description: SwiftLint and clippy give a function's length and not where it ends. A touched function is then found over as many lines as its length, so a change near its end is missed. Swift's tree and ast-grep's Rust rules could give the span.
- created: 2026-11-24
- found: the change to code lines
- related: [F4.9: Old smells in touched code](../features/F4-smells.md#f49-old-smells-in-touched-code)

---

### [P2][IDEA] INSTALL says what to do when an install fails

- description:
  - INSTALL has no part for a failed install, and nobody has recorded what one shows.
  - Every install so far ran on the author's machine, so the first install by a stranger is where the cases come from.
- created: 2026-11-20
- found: the docs pass of 2026-11-20
- related: [What it takes for a second user to install broom and stay](#p1discussion-what-it-takes-for-a-second-user-to-install-broom-and-stay)

---

### [P2][DISCUSSION] One open way to ask broom, in place of a flag per question

- description:
  - The user asked on 2026-11-18 for two things: a scope, excludes and limits that a call can set, and a way to ask broom anything, as Code Mode lets a model write code against an API.
  - The forms on the table: more flags · a full export of the measurements for a script outside broom · SQL over a database broom fills · one JSON query · a script that broom runs · a library to import.
  - The want "no script to write" and its goal say a session writes no script, which several of these forms reverse.
  - The user narrowed it that day: the ability sits inside broom, so that the command line needn't cover every case. An export for a script outside broom and a library are out.
  - The user rejected SQL over a database that day.
  - The user settled the stance behind it that day: broom holds no model, every analysis is the coding agent's, and broom hands the agent facts while it watches the agent for the user. The form of the open way is still open.
- created: 2026-11-18
- updated: 2026-11-18
- status: OPEN
- found: the user, in the session of 2026-11-18
- next: judge the forms by that stance

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

---

### [P2][IDEA] A test suite that gets slower

- description:
  - A suite slows a little with each change, and no change is at fault, which is rot by broom's own definition.
  - This repo's suite took about 40 seconds on 2026-11-17, 78 to 81 on 2026-11-19 and 113 to 150 on 2026-11-20, that day with other sessions busy on the machine.
  - broom sees each test run's command at a turn's end, so it could keep how long a run took and tell when that grew.
- created: 2026-11-19
- found: the look for missed rot at the end of CP6
- related: [F11.1: Counters](../features/F11-checkup.md#f111-counters)

---

### [P2][IDEA] A Go error dropped with the blank name

- description:
  - Go's `swallowed_error` finds an empty block. An error assigned to `_` is the commoner way to drop one, and nothing counts it.
  - errcheck finds it with `check-blank`. It needs types, so it would run in the real tree.
  - Rust's nearest form, a `Result` dropped with `let _ =`, is already a nit.
- created: 2026-11-19
- found: the look for missed rot at the end of CP10.1
- related: [F4.2: Occurrence smells](../features/F4-smells.md#f42-occurrence-smells)

---

### [P2][IDEA] broom says which smells a repo's languages lack

- description:
  - The user asked on 2026-11-19 how many smells each language measures, and the answer came from reading the code.
  - `broom doctor --checks` lists the checks that run. It could list, per language of the repo, the smells that language doesn't measure.
- created: 2026-11-19
- found: the user's question
- related: [F1.5: Protection list](../features/F1-setup.md#f15-protection-list)

---

### [P2][IDEA] Unsafe code as a counter

- description:
  - Rust's `unsafe` blocks, Go's `unsafe` package and Swift's unsafe pointers each step outside what the compiler checks.
  - A change that adds one is no smell broom knows, and nothing counts them across the repo, so a codebase can lean on them more each month with no change at fault.
  - The syntax trees of 0.26.0 make the count cheap and exact: an `unsafe_block` node in Rust, an import of `unsafe` in Go, a call to `withUnsafe…` in Swift.
- created: 2026-11-20
- found: the look for missed rot at the end of CP10
- related: [F11.1: Counters](../features/F11-checkup.md#f111-counters)

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

### [P2][IDEA] Suppressions in files broom reads no tree for

- description:
  - Since 0.27.0 a lint suppression is found only in a comment a syntax tree isolated, in Python, Swift, Go, Rust, TS/JS and CSS.
  - A `.vue` or `.svelte` file, a shell script or a YAML config can loosen a linter too, and no self-waiver tells it any more.
  - ast-grep bundles grammars for HTML, Bash and YAML, so their comments could be read the same way.
- created: 2026-11-20
- found: the look for missed rot at the end of CP11
- related: [F2.8: Self-waivers shown](../features/F2-sweep.md#f28-self-waivers-shown)

---

### [P2][IDEA] Counts in docs that drift from the code

- description:
  - A doc or an image that says how many things the code has goes stale when one is added, and no change to that doc is at fault.
  - The README's hero lists the 27 smells by name, and the docs say how many checks `broom doctor` runs and how many smells each language measures.
  - A counter could compare such a number with the code's own list, where a project names that list.
- created: 2026-11-20
- found: the look for missed rot at the end of CP9
- related: [F11.1: Counters](../features/F11-checkup.md#f111-counters)
