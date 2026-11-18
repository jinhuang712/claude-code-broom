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

- **Stance**:
  - [Clean as you go](../PHILOSOPHY.md#when-is-a-smell-cleaned)
  - [At three moments of Claude's flow](../PHILOSOPHY.md#when-may-a-check-interrupt)

---

## The kinds of rot

The list grows: each checkpoint's end looks for kinds broom still misses.

| Rot | Where broom meets it |
|---|---|
| A function, file or type that keeps growing | [F4.1: Sized smells](F4-smells.md#f41-sized-smells) |
| Copies of code | [F4.3: Duplicate code](F4-smells.md#f43-duplicate-code) |
| Modules that import one another | [F4.5: Cycles](F4-smells.md#f45-cycles) |
| Files that are bad and often changed | [F10.2: Hotspots by churn](F10-diagnosis.md#f102-hotspots-by-churn) |
| Lint suppressions that pile up | [F11.1: Counters](#f111-counters) |
| Skipped tests that pile up | [F11.1: Counters](#f111-counters) |
| TODO comments nobody comes back to | [F11.1: Counters](#f111-counters) |
| Code the tests never reach | [F11.2: Test coverage](#f112-test-coverage) |
| Tests that repeat one another | [F11.3: Duplicate tests](#f113-duplicate-tests) |
| Code nothing uses | [F11.4: Dead code in the whole repo](#f114-dead-code-in-the-whole-repo) |
| Public code with no comment | [F11.5: Missing comments](#f115-missing-comments) |
| Dependencies with known vulnerabilities | [F11.6: Dependencies](#f116-dependencies) |
| Packages nothing imports | [F11.6: Dependencies](#f116-dependencies) |
| Calls to deprecated APIs | [F11.7: Deprecated APIs](#f117-deprecated-apis) |

---

## F11.1: Counters

8 counters, none of which needs a tool installed beyond the ones the smells already use:

- Lint suppressions in the repo.
- Skipped tests in the repo.
- TODO comments older than 180 days.
- Dead-code findings in the whole repo.
- Public code with no doc comment.
- Calls to deprecated APIs.
- Duplicate test blocks.
- Lines no test reaches, by the project's own coverage report.

The first check-up of a repo takes its numbers silently, and so does the first after an update of broom. After that Claude is told once when a counter grew, with the old and the new value and up to three files that added to it, such as `broom check-up: lint suppressions 6 -> 9 (a.py, b.py)`. A counter that fell says nothing.

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

It uses the rule each language's linter already has: ruff's in Python, revive's in Go and SwiftLint's in Swift. oxlint has none, so in TS/JS a rule of broom's own looks at each exported function and class. Any comment that ends on the line above counts, and a lint directive does not. A private helper and a test need no comment.

2 gaps:

- In TS/JS a re-export, an exported type and a method are not looked at.
- The TS/JS rule needs Node, like broom's other rules for oxlint.

- **How it works**: [Check-up](../specs/checkup.md)

---

## F11.6: Dependencies

`broom diagnose` lists the packages each project declares and nothing imports, by name. It asks the tool each language has for that:

| Language | Tool | Comes with |
|---|---|---|
| TS/JS | knip | an install |
| Python | deptry | an install |
| Rust | cargo-machete | an install |
| Go | `go mod tidy -diff` | Go 1.23 or later |

A tool that isn't installed is named once in the report with its install command, and its language is not measured. Nothing asks for it at session start or at a commit. `broom doctor` lists these tools as optional, apart from the gaps. They run only in the diagnosis, since they take too long for a check on a change.

`broom diagnose --vulnerabilities` also asks osv-scanner for the known vulnerabilities of the packages in the lockfiles. The report lists each vulnerable package with its version, its worst level, its advisories and the version that fixes it. This sends package names and versions to OSV, a public database, so it runs only with the flag, and the report says what is sent.

2 gaps:

- cargo-machete's output is read as its docs give it and was never run here.
- Swift has no such tool in broom.

- **Design**: [7. Nothing is installed or set without a yes](../DESIGNS.md#7-nothing-is-installed-or-set-without-a-yes)
- **Commands**:
  - [broom diagnose](../CLI.md#broom-diagnose)
  - [broom doctor](../CLI.md#broom-doctor)
- **How it works**: [Diagnosis](../specs/diagnosis.md)
- **Why**:
  - [029: A tool broom can do without is listed and never asked for](../specs/decisions/029-optional-tools.md)
  - [030: Known vulnerabilities are looked up only on request](../specs/decisions/030-vulnerabilities-on-request.md)

---

## F11.7: Deprecated APIs

`deprecated_api` is a call to something its author marked as deprecated. A change that adds one gets a hint, and the hint carries the tool's own words, which usually name what replaced it. The check-up counts them across the repo.

It comes from the tools broom already runs:

| Language | From |
|---|---|
| Python | ruff's rules for the standard library · numpy · pandas · pytest |
| Go | staticcheck's `SA1019` |
| Rust | rustc's `deprecated` lint |
| TS/JS | oxlint's `typescript/no-deprecated`, which needs tsgolint |

Python's `typing.List` and its like are not counted, since every codebase older than Python 3.9 holds them and no version has dropped them.

3 gaps:

- Swift is not covered.
- TS/JS is measured only where tsgolint is installed, and `broom doctor` lists it as optional.
- Python's own `@deprecated` marks in a project are not seen, since ruff reads no types.

- **How it works**: [Smells](../specs/smells.md)
- **Why**: [029: A tool broom can do without is listed and never asked for](../specs/decisions/029-optional-tools.md)
