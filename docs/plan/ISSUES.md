# Issues

---

## Summary

```
Issues
├── docs
│   └── I1: The moved text doesn't meet the wording rules
├── refactor
│   ├── I2: Three paths call the same tools
│   ├── I5: Six rules sit on an alpha plugin API
│   ├── I6: The Bash parser guesses what git's hook knows
│   ├── I20: Swift's smells are read from text
│   ├── I21: Rust's smells are read from text
│   ├── I22: Go's three smells are read from text
│   └── I23: Skipped tests and the check-up's comment counters are read from text
└── fix
    └── I3: The cause of the reported Stop hang is unconfirmed
```

---

## I1: The moved text doesn't meet the wording rules

- type: docs
- why:
  - The changelog's sections before 0.18.2 keep their old wording, with long bullets of several commas.
  - README has no hero image.
- found: the docs pass, 2026-11-17
- next: [A hero image for the README](TODO.md#p2discussion-a-hero-image-for-the-readme)

---

## I2: Three paths call the same tools

- type: refactor
- why:
  - The lint check, the scratch copy and the real tree each start the same linters on the same files.
  - A cache keeps the base of a change from being measured twice, and the rest still runs more than once.
- found: a review of the hooks' cost, 2026-11-16
- touches:
  - [F2.1: Commit check](../features/F2-sweep.md#f21-commit-check)
  - [F4: Smells](../features/F4-smells.md)
- next: the ledger's seconds per tool, to say which run to keep

---

## I3: The cause of the reported Stop hang is unconfirmed

- type: fix
- why:
  - A Stop hook ran until Claude Code ended it at its timeout, 18 times in one session.
  - 0.18.1 removed every wait that had no bound.
  - The hang didn't reproduce here, so the cause on that machine is not known.
- found: a user's report, 2026-11-16
- touches:
  - [F2.7: Time limit](../features/F2-sweep.md#f27-time-limit)
- next: a `hook-trace.log` from the machine where it happened

---

## I5: Six rules sit on an alpha plugin API

- type: refactor
- why:
  - 6 smells in TS/JS come from rules of broom's own: `bool_params` · `type_lines` · `globals` · `commented_code` · `missing_docs` · `broad_catch`.
  - They load through oxlint's JS plugins, which oxlint's docs call alpha.
  - They need Node.
- found: a review of what broom wrote itself, 2026-11-17
- touches:
  - [F4.2: Occurrence smells](../features/F4-smells.md#f42-occurrence-smells)
- next: the fix rate of these six rules, to say whether to move them to another tool or drop them

---

## I6: The Bash parser guesses what git's hook knows

- type: refactor
- why: The commit hook reads a Bash command to predict the files a commit will take. git's own hook sees the staged files. The parser can go once git's hook is the norm and formatting at commit has another moment.
- found: a review of what broom wrote itself, 2026-11-17
- touches:
  - [F2.1: Commit check](../features/F2-sweep.md#f21-commit-check)
  - [F2.4: git's pre-commit hook](../features/F2-sweep.md#f24-gits-pre-commit-hook)
- next: [F2.4.1: Offered at setup](../features/F2-sweep.md#f241-offered-at-setup)

---

## I20: Swift's smells are read from text

- type: refactor
- why:
  - `swiftmeasure.py` counts braces for nesting, broad catches and dead code, after blanking strings and comments by hand.
  - 6 SwiftLint custom rules are regular expressions: `commented_code` · `broad_test_asserts` · `debug_output` · `globals` · `bool_params` · `nested_ternary`.
  - The Swift compiler's `-dump-parse` gives the same code as a JSON tree in about 60 ms a file.
- found: the user's ask for checks that hold up, 2026-11-20
- touches:
  - [9. A smell is read from a syntax tree, never from a text pattern](../DESIGNS.md#9-a-smell-is-read-from-a-syntax-tree-never-from-a-text-pattern)
  - [F8.6: Swift](../features/F8-languages.md#f86-swift)

---

## I21: Rust's smells are read from text

- type: refactor
- why:
  - `rustmeasure.py` reads 6 smells from text: `magic_numbers` · `commented_code` · `globals` · `type_lines` · `broad_test_asserts` · `broad_catch`.
  - `rustcycles.py` reads `use` statements with regular expressions.
  - The nested ternary, which the user settled on 2026-11-20 as a nested `if` expression, waits for this.
- found: the user's ask for checks that hold up, 2026-11-20
- touches:
  - [9. A smell is read from a syntax tree, never from a text pattern](../DESIGNS.md#9-a-smell-is-read-from-a-syntax-tree-never-from-a-text-pattern)
  - [F8.3: Rust](../features/F8-languages.md#f83-rust)

---

## I22: Go's three smells are read from text

- type: refactor
- why: `gomeasure.py` reads a type's length, a dropped `recover()` and a broad testify assertion from the text, on gofmt's layout.
- found: the user's ask for checks that hold up, 2026-11-20
- touches:
  - [9. A smell is read from a syntax tree, never from a text pattern](../DESIGNS.md#9-a-smell-is-read-from-a-syntax-tree-never-from-a-text-pattern)
  - [F8.1: Go](../features/F8-languages.md#f81-go)

---

## I23: Skipped tests and the check-up's comment counters are read from text

- type: refactor
- why:
  - `testrot.py` finds a skipped test in 5 languages by regular expressions, and Rust's own tests by `#[test]` in the text.
  - The check-up counts lint suppressions and TODO comments by matching lines, so a marker inside a string can count.
- found: the user's ask for checks that hold up, 2026-11-20
- touches:
  - [9. A smell is read from a syntax tree, never from a text pattern](../DESIGNS.md#9-a-smell-is-read-from-a-syntax-tree-never-from-a-text-pattern)
  - [F4.2.2: Skipped test](../features/F4-smells.md#f422-skipped-test)
  - [F11.1: Counters](../features/F11-checkup.md#f111-counters)

