# F4: Smells

```
F4: Smells
├── F4.1: Sized smells — a hint past the soft limit, a block past the hard one
├── F4.2: Occurrence smells — a change that adds one gets its level
│   ├── F4.2.1: Broad catch — a handler that takes every error
│   ├── F4.2.2: Skipped test
│   └── F4.2.3: Untested file
├── F4.3: Duplicate code — a new copy anywhere in the repo
├── F4.4: Dead code — code a change adds and nothing uses
├── F4.5: Cycles — imports that lead back
│   ├── F4.5.1: Import cycle
│   └── F4.5.2: Folder cycle
├── F4.6: What is skipped — dependencies, build output and generated code
├── F4.7: Tests — measured by rules of their own
├── F4.8: Limits told before the work — Claude knows the bar when it starts
└── F4.9: Old smells in touched code — whoever is in the code cleans it
```

A smell is code that works and is hard to change. broom measures smells against its own limits in every repo. What a change made worse counts, and so does an old smell in the code it touches. Code a change doesn't touch never comes up.

A smell has 1 of 3 levels. A hint and a block both stop a commit and a turn's end, and pass only fixed or accepted with a reason. A block is past the hard limit, and one that was there and grew can't be accepted. A nit is a slight smell, or one a detector guesses: it is told and stops nothing. The `smells` setting turns them all off, and `smells_off` in `.broom.json` turns single ones off.

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
| `nesting` | 4 | 6 | `PLR1702` | `max-depth` | `nestif` | read by broom |
| `complexity` | 10 | 20 | `C901` | `complexity` | `gocognit` | `cyclomatic_complexity` |
| `nested_ternary` | — | any | `ast` | `no-nested-ternary` | — | a custom rule |
| `type_lines` | 250 | — | `ast` | `broom/class-lines` | read by broom | `type_body_length` |
| `duplicate_lines` | 10 | 30 | jscpd | jscpd | jscpd | jscpd |

9 notes on the table:

- `file_lines` and `duplicate_lines` count in Rust and CSS too.
- Go has no ternary operator, so it has no `nested_ternary`.
- Go's `type_lines` is a type's declaration plus its methods in the same file.
- Rust gets 4 of them from clippy: `function_lines` from `too_many_lines` · `params` from `too_many_arguments` · `complexity` from `cognitive_complexity` · `nesting` from `excessive_nesting`.
- Rust's `nesting` only hints, since clippy names no depth.
- Rust's `type_lines` is read by broom, as Go's is: a `struct`, `enum`, `trait` or `union` plus its `impl` blocks in the same file.
- Rust has no `nested_ternary` yet: a nested `if` expression counts as one and is still to be measured.
- Swift's `nesting` counts the blocks of control flow inside a function, since SwiftLint's own rule counts nested types.
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
| `commented_code` | block | `ERA001` | `broom/commented-code` | `gocritic` `commentedOutCode` | a custom rule |
| `unused_params` | hint | `ARG` | `no-unused-vars` | `revive` `unused-parameter` | `unused_parameter` |
| `magic_numbers` | nit | `PLR2004` | `no-magic-numbers` | `mnd` | `no_magic_numbers` |
| `debug_output` | hint | `T201` `T203` | `no-console` | `forbidigo` | a custom rule |
| `todo` | nit | `FIX` | `no-warning-comments` | `godox` | `todo` |
| `type_escape` | hint | `ANN401` | `no-explicit-any` `no-non-null-assertion` | `revive` `unchecked-type-assertion` | `force_cast` `force_unwrapping` `force_try` |
| `globals` | hint | `PLW0603` | `broom/module-state` | `gochecknoglobals` | a custom rule |
| `bool_params` | hint | `FBT001` | `broom/bool-params` | `revive` `flag-parameter` | a custom rule |
| `broad_test_asserts` | hint | `PT011` | `jest/require-to-throw-message` | read by broom | a custom rule |
| `broad_catch` | hint | `BLE001` `E722` | `broom/broad-catch` | read by broom | read by broom |
| `missing_docs` | hint | `D100` `D101` `D102` `D103` | `broom/missing-docs` | `revive` `exported` | `missing_docs` |
| `deprecated_api` | hint | `UP` and others | `typescript/no-deprecated` | `staticcheck` `SA1019` | `swiftc` `DeprecatedDeclaration` |
| `skipped_test` | hint | read by broom | read by broom | read by broom | read by broom |
| `untested_file` | nit | read by broom | read by broom | read by broom | read by broom |

12 notes on the table:

- `commented_code` is a nit in TS/JS, Go, Swift and Rust, whose detectors guess.
- Go's `commented_code` is found inside a function and missed at the top level of a file.
- TS/JS's `no-unused-vars` counts parameters only.
- Unused variables and imports stay with the project's linter, which already reports them.
- Swift's `debug_output` rule finds 4 calls: `print` · `debugPrint` · `NSLog` · `dump`.
- Swift's `globals` rule finds a `var` at file level, `main.swift` aside.
- Swift's `bool_params` rule finds an unlabeled `_ flag: Bool`.
- A function handed to a call is the callee's choice and doesn't count for `bool_params`.
- `module-state` is a `let` or `var` at module level that a function assigns.
- Go's `broad_test_asserts` is a testify `Error` or `Panics`, which any error passes.
- Swift's `broad_test_asserts` is an `XCTAssertThrowsError` with no handler, or an `#expect` or `#require` that any `Error` passes.
- Swift's `deprecated_api` comes from type-checking the changed files of a SwiftPM package, so an Xcode project is left out.

Rust gets 9 of these from clippy and rustc: `suppression` · `swallowed_error` · `unused_params` · `debug_output` · `todo` · `type_escape` · `bool_params` · `deprecated_api` · `missing_docs`. broom reads 5 more from its text: `magic_numbers` · `commented_code` · `globals` · `broad_test_asserts` · `broad_catch`. A Rust global is a `static mut`, a `static` that holds a lock, a cell or an atomic, or a `thread_local!`, and a plain `static` is a constant. A broad test assertion is a `#[should_panic]` with no `expected`, or an `assert!` that any `Err` passes. Its `skipped_test` is an `#[ignore]`, read by broom. Its `swallowed_error` is a `Result` dropped with `let _ =`, and it is a nit, since that can be deliberate. Its `todo` is a `todo!()` or an `unimplemented!()`. Test code is not built, so a test may be long, unwrap and print. CSS, SCSS and Less have no smell tool.

The five `broom/` rules need Node. Without it only these smells go unmeasured, and a note says so.

- **Why**: [009: An occurrence counts when the change raises the count](../specs/decisions/009-occurrence-by-count.md)

---

### F4.2.1: Broad catch

`broad_catch` is an error handler that takes every error alike. It hides the error it wasn't written for. A change that adds one gets a hint.

It has 1 form per language:

| Language | What counts | What stays quiet |
|---|---|---|
| Python | a bare `except` · an `except Exception` | a handler that re-raises |
| TS/JS | a `catch` or a `.catch()` callback that never reads its error | a handler that throws |
| Go | a `recover()` whose value is dropped | a `recover()` whose value is read |
| Swift | a `catch` that never reads its error | a `catch` of a named error type · a handler that throws · `try?` |
| Rust | an `Err(_) =>` arm · a `.map_err(\|_\| …)` · a dropped `catch_unwind` | an arm that binds the error |

TS/JS can't catch by type, so there a handler has to look at what it caught. An empty `catch` is a `swallowed_error`. Swift's `try?` drops every error too, and it is left out, since it is the language's common way to say an error doesn't matter.

---

### F4.2.2: Skipped test

`skipped_test` is a test a change marks as skipped or disabled. It is the shortest way to make a failing suite pass. A change that adds one gets a hint.

It covers Python, TS/JS, Go, Rust and Swift, and it needs no tool: broom reads the test files' text. A skip that a condition decides doesn't count, such as `skipUnless` or a `t.Skip` under an `if`. That is how a suite fits the machine it runs on. `broom stats` and the check-up still count those.

---

### F4.2.3: Untested file

`untested_file` is a code file a change adds with no test file named for it anywhere in the repo, such as `foo.py` with no `test_foo.py`. A change that adds one gets a nit. It needs no tool.

A file of fewer than 30 non-blank lines is left alone. So are `__init__.py` and `conftest.py`.

A Rust file is tested when it holds a `#[test]` or a `#[cfg(test)]`, or when a file such as `tests/<name>.rs` is named for it. `main.rs`, `lib.rs`, `mod.rs` and `build.rs` are left alone.

2 gaps:

- The pairing goes by file name, so a test named otherwise is missed.
- CSS takes no part, since it has no such naming.

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

A file, export, symbol or import that nothing uses gets a nit when the change added it. It covers TS/JS and Python, with tests and entry points left out, unexported code in Go, what rustc calls dead in Rust and a `private` or `fileprivate` declaration nothing in its file names in Swift. Swift's `internal` code is not read, since its uses may lie anywhere in the module.

What loads dynamically, such as a manifest's scripts or plugins, looks unused too. `smells_off: ["dead_code"]` turns it off per repo.

- **Why**: [013: Dead code counts on added lines](../specs/decisions/013-dead-code-added-lines.md)

---

## F4.5: Cycles

Both are hints, and both count where the change adds the import.

- **Why**: [014: No layering rules without a project's own](../specs/decisions/014-no-layering-rules.md)

---

### F4.5.1: Import cycle

`import_cycle` is a module importing back what imports it. It covers Python, TS/JS and Rust, where a `use` of the same crate counts. In Python an import inside a function or under `if TYPE_CHECKING:` doesn't count. Swift rules it out: a Swift file imports modules and never another file, and SwiftPM refuses modules that depend on one another.

---

### F4.5.2: Folder cycle

`folder_cycle` is an import that leads into a folder whose files lead back to this one, such as `auth` importing `providers` while `providers` imports `auth`. It covers Python, TS/JS and Rust.

TS/JS needs dependency-cruiser, which reads a `.ts` file only with a TypeScript below 7 beside it. So broom keeps a copy of its own with a TypeScript 6, and a project on TypeScript 7 is read like any other. `broom doctor` offers the copy as one command, and it changes nothing in the project or in the user's own TypeScript. Without a dependency-cruiser that can read the repo nothing is measured and nothing nags. Go refuses package cycles itself. Swift rules it out too: the files of one module don't import one another, and SwiftPM refuses modules that do.

- **Why**: [036: broom keeps its own dependency-cruiser](../specs/decisions/036-own-dependency-cruiser.md)

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

---

## F4.8: Limits told before the work

At the start of a session in a repo with code, Claude is told the bar in a few lines: how long a function and a file may be, how many parameters, how deep the nesting and how high the complexity, each with the size past which a change is blocked. It also names what blocks for being added, how a blocked finding passes and which broom command answers a question about the repo.

The numbers are the repo's own, so limits moved in `.broom.json` show, and a smell the repo turned off is left out. A repo with no code, or with `smells` off, gets no card. It is told once per session.

- **How it works**: [Setup](../specs/setup.md)

---

## F4.9: Old smells in touched code

When a change touches a function, a type or a file that already holds a sized smell, Claude is told to clean it in the same change. The finding says `you touched it, clean it up in this change`, so it reads apart from a smell the change made worse. It is a hint: it stops a commit and a turn's end, and passes with a reason.

A function or a type is touched when a changed line lies inside it. A file is touched when it gained code lines besides imports. Code the change doesn't touch stays quiet, and so does a file that was only renamed.

A function, a type or a file that was already past the hard limit and that the change grew can't be accepted. The block marks that line, and `broom known --accept` leaves it out and says what size to bring it back to. A smell that is newly past the hard limit can be accepted as before.

2 gaps:

- Outside Python a touched function is told its length only, since the tools give no range for the other sized smells.
- A touched Go type isn't told, since its methods lie apart in the file.

In Rust a touched function that is too long is told.

- **Stance**: [Clean as you go](../PHILOSOPHY.md#when-is-a-smell-cleaned)
- **How it works**: [Smells](../specs/smells.md)
- **Why**: [028: A change is told the old smells in the code it touches](../specs/decisions/028-old-smells-in-touched-code.md)
