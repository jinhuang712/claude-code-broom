# F11: Check-up

```
F11: Check-up
├── F11.1: Counters — numbers that speak only when they grow
├── F11.2: Test coverage — code the tests never reach
├── F11.3: Duplicate tests — tests that repeat one another
├── F11.4: Dead code in the whole repo — what nothing uses any more
├── F11.5: Missing comments — public code with no word on what it is for
├── F11.6: Dependencies — known vulnerabilities and unused packages
└── F11.7: Deprecated APIs — calls a library's author says to stop using
```

A check-up looks for rot: things that get worse without any one change being at fault. It covers the whole repo, runs in the background at session start and never blocks. It speaks only when a number is worse than the last time.

The same numbers go into the whole-repo diagnosis, where every one is listed whether it grew or not.

- **Stance**: [Clean as you go](../PHILOSOPHY.md#when-is-a-smell-cleaned) · [Never in the way](../PHILOSOPHY.md#when-may-a-check-interrupt)

---

## The kinds of rot

The list grows: each checkpoint's end looks for kinds broom still misses.

| Rot | Where broom meets it |
|---|---|
| A function, file or type that keeps growing | [F4.1: Sized smells](F4-smells.md#f41-sized-smells) |
| Copies of code | [F4.3: Duplicate code](F4-smells.md#f43-duplicate-code) |
| Modules that import one another | [F4.5: Cycles](F4-smells.md#f45-cycles) |
| Files that are bad and often changed | [F10.2: Hotspots by churn](F10-diagnosis.md#f102-hotspots-by-churn) |
| Lint suppressions that pile up | F11.1 |
| Skipped tests that pile up | F11.1 |
| TODO comments nobody comes back to | F11.1 |
| Code the tests never reach | F11.2 |
| Tests that repeat one another | F11.3 |
| Code nothing uses | F11.4 |
| Public code with no comment | F11.5 |
| Dependencies with known vulnerabilities | F11.6 |
| Packages nothing imports | F11.6 |
| Calls to deprecated APIs | F11.7 |

---

## F11.1: Counters

3 counters, none of which needs a tool installed:

- Lint suppressions in the repo.
- Skipped tests in the repo.
- TODO comments older than six months.

Claude is told once when a counter grew since the last check-up, with the files that added to it.

---

## F11.2: Test coverage

broom reads the coverage report a project's own test run already wrote, such as `coverage.xml`, `lcov.info` or Go's cover profile. It doesn't run the tests.

It reports 2 things:

- Files and functions no test reaches, worst first.
- Coverage that fell since the last check-up.

Without a report it says once how to produce one and then stays quiet. A change that adds a code file with no test beside it gets a hint.

---

## F11.3: Duplicate tests

Tests that repeat one another are listed in the check-up and the diagnosis, with the lines they share. The checks on a change still leave clones between two test files out.

---

## F11.4: Dead code in the whole repo

Files, exports and symbols nothing uses are counted across the repo, not only on the lines a change added. The check-up tells Claude when the count grew, and the diagnosis lists them all.

---

## F11.5: Missing comments

Public code with no comment on what it is for is counted: an exported function, type or module without a doc comment. A change that adds one gets a hint.

It uses the rule each language's linter already has. A private helper and a test need no comment.

---

## F11.6: Dependencies

Known vulnerabilities and unused packages are reported where the user installed a tool for them. Without the tool nothing is measured and nothing nags. `broom doctor` offers the tools.

A check that looks a package up on the network is off until the user turns it on.

- **Design**: [7. Nothing is installed or set without a yes](../DESIGNS.md#7-nothing-is-installed-or-set-without-a-yes)

---

## F11.7: Deprecated APIs

A call to a deprecated API is reported through the linters broom already runs. It needs no tool installed.
