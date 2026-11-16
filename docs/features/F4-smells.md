# F4: Smells

```
F4: Smells
├── F4.1: Sized smells — a hint past the soft limit, a block past the hard one
├── F4.2: Occurrence smells — a change that adds one gets its level
├── F4.3: Duplicate code — a new copy anywhere in the repo
├── F4.4: Dead code — code a change adds and nothing uses
├── F4.5: Cycles — imports that lead back
│   ├── F4.5.1: Import cycle
│   └── F4.5.2: Folder cycle
├── F4.6: What is skipped — dependencies, build output and generated code
└── F4.7: Tests — measured by rules of their own
```

A smell is code that works and is hard to change. broom measures smells against its own limits in every repo, and only what a change made worse counts. Legacy code left as it was never comes up.

A hint goes into the commit's context and stops a turn's end once. A block stops the commit and passes only fixed or accepted with a reason. The `smells` setting turns them all off, and `smells_off` in `.broom.json` turns single ones off.

- **Stance**: [One bar for smells](../PHILOSOPHY.md#whose-bar-measures-a-code-smell)
- **Design**: [4. A finding counts only where the change made things worse](../DESIGNS.md#4-a-finding-counts-only-where-the-change-made-things-worse)
- **How it works**: [Smells](../specs/smells.md)
- **Why**:
  - [005: Smells are measured by broom's limits in a scratch copy](../specs/decisions/005-own-bar-scratch-copy.md)
  - [016: A smell past the hard limit blocks like a type error](../specs/decisions/016-severe-smells.md)

---

## F4.1: Sized smells

A sized smell counts when the change pushed it past a limit, or grew it while past the hard one. Growth between the limits is left alone.

| Smell | Soft | Hard | Python | TS/JS | Go | Swift |
|---|---|---|---|---|---|---|
| `function_lines` | 50 | 100 | `ast` | `max-lines-per-function` | `funlen` | `function_body_length` |
| `file_lines` | 400 | 1000 | counted | counted | counted | counted |
| `params` | 5 | 8 | `PLR0913` | `max-params` | `revive` `argument-limit` | `function_parameter_count` |
| `nesting` | 4 | 6 | `PLR1702` | `max-depth` | `nestif` | — |
| `complexity` | 10 | 20 | `C901` | `complexity` | `gocognit` | `cyclomatic_complexity` |
| `nested_ternary` | — | any | `ast` | `no-nested-ternary` | — | a custom rule |
| `type_lines` | 250 | — | `ast` | `broom/class-lines` | — | `type_body_length` |
| `duplicate_lines` | 10 | 30 | jscpd | jscpd | jscpd | jscpd |

4 notes on the table:

- `file_lines` and `duplicate_lines` count in Rust and CSS too.
- Rust's `params` comes from clippy's `too_many_arguments`.
- Swift has no control-flow nesting rule, and complexity covers it.
- Swift's nested-ternary rule finds two ternary operators on one line.

A file git sees as renamed is measured against its old path. A file whose lines besides imports didn't grow isn't longer for the change.

- **Why**:
  - [006: A smell counts when the change pushed it past a limit](../specs/decisions/006-made-worse.md)
  - [007: A renamed file is measured against its old path](../specs/decisions/007-renames-and-imports.md)

---

## F4.2: Occurrence smells

A change that adds an occurrence gets the smell's level. An occurrence counts when the change raises the count in a file. A moved line stays old, and a line counts once per smell.

| Smell | Level | Python | TS/JS | Go | Swift |
|---|---|---|---|---|---|
| `suppression` | block | `PGH003` `PGH004` | `ban-ts-comment` | `nolintlint` | `blanket_disable_command` |
| `swallowed_error` | block | `S110` | `no-empty` `no-useless-catch` | `revive` `empty-block` | `no_empty_block` |
| `commented_code` | block | `ERA001` | `broom/commented-code` | `gocritic` `commentedOutCode` | — |
| `unused_params` | hint | `ARG` | `no-unused-vars` | `revive` `unused-parameter` | `unused_parameter` |
| `magic_numbers` | hint | `PLR2004` | `no-magic-numbers` | `mnd` | `no_magic_numbers` |
| `debug_output` | hint | `T201` `T203` | `no-console` | `forbidigo` | a custom rule |
| `todo` | hint | `FIX` | `no-warning-comments` | `godox` | `todo` |
| `type_escape` | hint | `ANN401` | `no-explicit-any` `no-non-null-assertion` | `revive` `unchecked-type-assertion` | `force_cast` `force_unwrapping` `force_try` |
| `globals` | hint | `PLW0603` | `broom/module-state` | `gochecknoglobals` | a custom rule |
| `bool_params` | hint | `FBT001` | `broom/bool-params` | `revive` `flag-parameter` | a custom rule |
| `broad_test_asserts` | hint | `PT011` | `jest/require-to-throw-message` | — | — |

8 notes on the table:

- `commented_code` is a hint in TS/JS and Go, whose detectors guess.
- TS/JS's `no-unused-vars` counts parameters only.
- Unused variables and imports stay with the project's linter, which already reports them.
- Swift's `debug_output` rule finds `print`, `debugPrint`, `NSLog` and `dump`.
- Swift's `globals` rule finds a `var` at file level, `main.swift` aside.
- Swift's `bool_params` rule finds an unlabeled `_ flag: Bool`.
- A function handed to a call is the callee's choice and doesn't count for `bool_params`.
- `module-state` is a `let` or `var` at module level that a function assigns.

Rust gets 5 of these from clippy: `bool_params` · `debug_output` · `type_escape` · `suppression` · `params`. A test may unwrap and print. CSS, SCSS and Less have no smell tool.

The four `broom/` rules need Node. Without it only these smells go unmeasured, and a note says so.

- **Why**: [009: An occurrence counts when the change raises the count](../specs/decisions/009-occurrence-by-count.md)

---

## F4.3: Duplicate code

A new duplicate block with a side in the change's files hints past 10 lines and blocks past 30. It is found anywhere in the repo, and compared with the base so old copies stay quiet.

3 kinds of clone don't count:

- Clones between two test files.
- Clones of generated or vendored code.
- Clones with a side in `.broom.json` `legacy`.

It needs jscpd 5, which `broom doctor` checks for.

- **Why**:
  - [010: Duplicate code is found across the whole repo](../specs/decisions/010-whole-repo-clones.md)
  - [011: Code marked legacy may be repeated](../specs/decisions/011-legacy.md)

---

## F4.4: Dead code

A file, export, symbol or import that nothing uses gets a hint when the change added it. It covers TS/JS and Python, with tests and entry points left out, and unexported code in Go.

What loads dynamically, such as a manifest's scripts or plugins, looks unused too. `smells_off: ["dead_code"]` turns it off per repo.

- **Why**: [013: Dead code counts on added lines](../specs/decisions/013-dead-code-added-lines.md)

---

## F4.5: Cycles

Both are hints, and both count where the change adds the import.

- **Why**: [014: No layering rules without a project's own](../specs/decisions/014-no-layering-rules.md)

---

### F4.5.1: Import cycle

`import_cycle` is a module importing back what imports it. It covers Python and TS/JS. In Python an import inside a function or under `if TYPE_CHECKING:` doesn't count.

---

### F4.5.2: Folder cycle

`folder_cycle` is an import that leads into a folder whose files lead back to this one, such as `auth` importing `providers` while `providers` imports `auth`. It covers Python and TS/JS.

TS/JS needs dependency-cruiser and a TypeScript below 7 next to it. `broom doctor` offers it. Without it nothing is measured and nothing nags. Go refuses package cycles itself. Swift and Rust aren't read.

---

## F4.6: What is skipped

Dependencies, environments, build output, generated code, fixtures, minified files and `.d.ts` are skipped.

4 groups of names:

- **Dependencies and environments**: `node_modules` · `vendor` · `Pods` · `Carthage` · `.venv` · `venv` · `site-packages` · `__pycache__`.
- **Build output**: `.build` · `DerivedData` · `dist` · `.bundle` · `.next` · `coverage` · `test-results`.
- **Generated code and fixtures**: `Generated` · `generated` · `testdata` · files headed `DO NOT EDIT` or `@generated`.
- **Only where git doesn't track them**: `build` · `out` · `release` · `target`.

Tracked directories skipped by name are listed in a note.

- **Why**: [008: Build-output names skip only untracked files](../specs/decisions/008-tracked-build-names.md)

---

## F4.7: Tests

In tests, complexity and magic numbers don't count. Neither do the length or complexity of `describe`, `it` and `test` callbacks. Long test functions still count. `test_limits` in `.broom.json` moves the limits for test files.

- **Why**: [012: Tests take limits of their own](../specs/decisions/012-test-limits.md)
