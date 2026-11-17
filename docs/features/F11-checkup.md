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

7 counters, none of which needs a tool installed beyond the ones the smells already use:

- Lint suppressions in the repo.
- Skipped tests in the repo.
- TODO comments older than 180 days.
- Dead-code findings in the whole repo.
- Public code with no doc comment.
- Duplicate test blocks.
- Lines no test reaches, by the project's own coverage report.

The first check-up of a repo takes its numbers silently. After that Claude is told once when a counter grew, with the old and the new value and up to three files that added to it, such as `broom check-up: lint suppressions 6 -> 9 (a.py, b.py)`. A counter that fell says nothing.

`smells_off: ["checkup"]` in `.broom.json` turns it off. A repo of more than 5,000 files gets no check-up at session start, and `broom diagnose` lists its counters instead.

- **Commands**: [broom diagnose](../CLI.md#broom-diagnose)
- **How it works**: [Check-up](../specs/checkup.md)

---

## F11.2: Test coverage

broom reads the coverage report a project's own test run already wrote. It doesn't run the tests.

It reads 4 forms of report, at the repo's root or in its `coverage` folder:

- Cobertura XML, such as the `coverage.xml` that `coverage xml` writes.
- lcov, such as `lcov.info`.
- Go's cover profile, such as `coverage.out`.
- The JSON of coverage.py, as `coverage.json`.

It reports 2 things:

- `broom stats` and `broom diagnose` give the share of lines a test reached and the files with most lines none did, worst first. They say how old the report is and whether it is older than the last commit.
- The check-up counts the lines no test reaches, so Claude is told once when a newer report shows more of them.

Without a report nothing is counted and nothing is told at session start. `broom stats` then names the command that writes one for each language of the repo. Test files are left out of the numbers.

2 gaps:

- Functions no test reaches are not listed, only files.
- The JSON that Istanbul writes is not read, and Swift gets no command for a report.

- **Commands**: [broom stats](../CLI.md#broom-stats)
- **How it works**: [Stats](../specs/stats.md)

---

## F11.3: Duplicate tests

Tests that repeat one another are listed by `broom diagnose`, the largest first, with both places and the lines they share. The check-up counts them, each on the file that was written last, and tells Claude once when there are more.

A block counts past the duplicate limit of tests. Generated tests and tests in `legacy` are left out. The checks on a change still leave clones between two test files out.

It needs jscpd. Without it nothing is counted, and the diagnosis says it was not measured.

- **Commands**: [broom diagnose](../CLI.md#broom-diagnose)
- **How it works**: [Check-up](../specs/checkup.md)

---

## F11.4: Dead code in the whole repo

Files, exports and symbols nothing uses are counted across the repo, not only on the lines a change added. The check-up tells Claude when the count grew, and `broom diagnose` lists them all.

- **How it works**: [Check-up](../specs/checkup.md)

---

## F11.5: Missing comments

`missing_docs` is public code with no comment on what it is for: a module, a class or a function with no doc comment. A change that adds one gets a hint, and the check-up counts them across the repo.

It uses the rule each language's linter already has: ruff's in Python, revive's in Go and SwiftLint's in Swift. A private helper and a test need no comment.

1 gap:

- TS/JS is not covered, since oxlint has no rule that asks for a doc comment.

- **How it works**: [Check-up](../specs/checkup.md)

---

## F11.6: Dependencies

Known vulnerabilities and unused packages are reported where the user installed a tool for them. Without the tool nothing is measured and nothing nags. `broom doctor` offers the tools.

A check that looks a package up on the network is off until the user turns it on.

- **Design**: [7. Nothing is installed or set without a yes](../DESIGNS.md#7-nothing-is-installed-or-set-without-a-yes)

---

## F11.7: Deprecated APIs

A call to a deprecated API is reported through the linters broom already runs. It needs no tool installed.
