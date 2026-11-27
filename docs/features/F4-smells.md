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
├── F4.7: Tests — only what lets a test lie stops a change
├── F4.8: Limits told before the work — Claude knows the bar when it starts
└── F4.9: Old smells in touched code — whoever is in the code cleans it
```

A smell is code that works and is hard to change. broom measures smells against its own limits in every repo. What a change made worse counts, and so does an old smell in the code it touches. Code a change doesn't touch never comes up.

A smell has 1 of 3 levels. A hint and a block both stop a commit and a turn's end, and pass only fixed or accepted with a reason. A block is past the hard limit, and one that was there and grew can't be accepted. A nit is a slight smell, one a detector guesses, or a test's shape: it is told and stops nothing. The `smells` setting turns them all off, and `smells_off` in `.broom.json` turns single ones off.

- **Stance**: [One bar for smells](../PHILOSOPHY.md#whose-bar-measures-a-code-smell)
- **Design**: [4. A finding counts only where the change made things worse](../DESIGNS.md#4-a-finding-counts-only-where-the-change-made-things-worse)
- **How it works**: [Smells](../specs/smells.md)
- **Why**:
  - [005: Smells are measured by broom's limits in a scratch copy](../specs/decisions/005-own-bar-scratch-copy.md)
  - [016: A smell past the hard limit blocks like a type error](../specs/decisions/016-severe-smells.md)

---

## F4.1: Sized smells

A sized smell counts when the change pushed it past a limit, or grew it while past the hard one. Growth between the limits is left alone.

3 of them are lengths: `function_lines`, `type_lines` and `file_lines`. A length counts code lines. A code line holds something besides space outside a comment, so a comment line and a blank line never count, and a change that adds only those grows nothing. A line with code and a comment beside it is a code line.

| Language | A comment is | Read with |
|---|---|---|
| Python | a `#` comment · the docstring of a module, a class or a function | `tokenize` and `ast` |
| TS/JS | a `//` or a `/* */` comment, JSDoc among them | ast-grep |
| Go | a `//` or a `/* */` comment, doc comments among them | ast-grep |
| Rust | a `//` or a `/* */` comment, `///` and `//!` among them | ast-grep |
| Swift | a `//` or a `/* */` comment, `///` among them | SourceKit |
| CSS, SCSS and Less | a `/* */` comment · a `//` comment in SCSS and Less | ast-grep |

3 things still count:

- A string over several lines counts on each of its lines that isn't blank, a Python string that is no docstring among them.
- An attribute that documents, such as Rust's `#[doc = "…"]`, is code.
- Without ast-grep, or without SourceKit for Swift, comments can't be told from code in that language. Every line that isn't blank then counts, and a note says so.

`read by broom` in the tables means broom reads the smell from the file's syntax tree: Python's with its own parser, Swift's with its compiler and SourceKit, and the others' with ast-grep. A string or a comment that looks like code is never taken for it.

| Smell | Soft | Hard | Python | TS/JS | Go | Swift |
|---|---|---|---|---|---|---|
| `function_lines` | 50 | 100 | `ast` | `max-lines-per-function` | read by broom | `function_body_length` |
| `file_lines` | 400 | 1000 | counted | counted | counted | counted |
| `params` | 5 | 8 | `PLR0913` | `max-params` | `revive` `argument-limit` | `function_parameter_count` |
| `nesting` | 4 | 6 | `PLR1702` | `max-depth` | `nestif` | read by broom |
| `complexity` | 10 | 20 | `C901` | `complexity` | `gocognit` | `cyclomatic_complexity` |
| `nested_ternary` | — | any | `ast` | `no-nested-ternary` | — | read by broom |
| `type_lines` | 250 | — | `ast` | `broom/class-lines` | read by broom | `type_body_length` |
| `duplicate_lines` | 10 | 30 | jscpd | jscpd | jscpd | jscpd |

13 notes on the table:

- `file_lines` and `duplicate_lines` count in Rust and CSS too.
- A test file's `file_lines` limits are twice these: 800 and 2000.
- A function's or a type's length runs from its first line through its last. Go's function starts at its `func` line and ends at its closing brace. Without ast-grep it goes unmeasured, with a note.
- Swift's function and type lengths and Rust's function length are the code lines of the body alone, as SwiftLint and clippy count them.
- `duplicate_lines` counts the code lines of the repeated block on the side measured, so a block of comments and blank lines is no clone.
- Go has no ternary operator, so it has no `nested_ternary`.
- Go's `type_lines` is a type's declaration plus its methods in the same file.
- Rust gets 4 of them from clippy: `function_lines` from `too_many_lines` · `params` from `too_many_arguments` · `complexity` from `cognitive_complexity` · `nesting` from `excessive_nesting`.
- Rust's `nesting` only hints, since clippy names no depth.
- Rust's `type_lines` is read by broom, as Go's is: a `struct`, `enum`, `trait` or `union` plus its `impl` blocks in the same file.
- Rust's `nested_ternary` is an `if` that gives a value and holds another such `if` in a branch. An `else if` chain stays flat and doesn't count.
- Swift's `nesting` counts the blocks of control flow inside a function, since SwiftLint's own rule counts nested types.
- Swift's `nested_ternary` is a ternary inside another, wherever its lines break.

A file git sees as renamed is measured against its old path. A file whose code lines besides imports didn't grow isn't longer for the change.

- **Why**:
  - [006: A smell counts when the change pushed it past a limit](../specs/decisions/006-made-worse.md)
  - [007: A renamed file is measured against its old path](../specs/decisions/007-renames-and-imports.md)
  - [039: A length counts code lines](../specs/decisions/039-code-lines.md)

---

## F4.2: Occurrence smells

A change that adds an occurrence gets the smell's level. An occurrence counts when the change raises the count in a file. A moved line stays old, and a line counts once per smell.

| Smell | Level | Python | TS/JS | Go | Swift |
|---|---|---|---|---|---|
| `suppression` | block | `PGH003` `PGH004` | `ban-ts-comment` | `nolintlint` | `blanket_disable_command` |
| `swallowed_error` | block | `S110` | `no-empty` `no-useless-catch` | `revive` `empty-block` | `no_empty_block` |
| `commented_code` | block | `ERA001` | `broom/commented-code` | `gocritic` `commentedOutCode` | read by broom |
| `unused_params` | hint | `ARG` | `no-unused-vars` | `revive` `unused-parameter` | `unused_parameter` |
| `magic_numbers` | nit | `PLR2004` | `no-magic-numbers` | `mnd` | `no_magic_numbers` |
| `debug_output` | hint | `T201` `T203` | `no-console` | read by broom | read by broom |
| `todo` | nit | `FIX` | `no-warning-comments` | `godox` | `todo` |
| `type_escape` | hint | `ANN401` | `no-explicit-any` `no-non-null-assertion` | `revive` `unchecked-type-assertion` | `force_cast` `force_unwrapping` `force_try` |
| `globals` | hint | `PLW0603` | `broom/module-state` | read by broom | read by broom |
| `bool_params` | hint | `FBT001` | `broom/bool-params` | `revive` `flag-parameter` | read by broom |
| `broad_test_asserts` | hint | `PT011` | `jest/require-to-throw-message` | read by broom | read by broom |
| `broad_catch` | hint | `BLE001` `E722` | `broom/broad-catch` | read by broom | read by broom |
| `missing_docs` | hint | `D100` `D101` `D102` `D103` | `broom/missing-docs` | `revive` `exported` | `missing_docs` |
| `deprecated_api` | hint | `UP` and others | `typescript/no-deprecated` | `staticcheck` `SA1019` | `swiftc` `DeprecatedDeclaration` |
| `skipped_test` | hint | read by broom | read by broom | read by broom | read by broom |
| `untested_file` | nit | read by broom | read by broom | read by broom | read by broom |

16 notes on the table:

- `commented_code` is a nit in TS/JS, Go, Swift and Rust, whose detectors guess.
- Go's `commented_code` is found inside a function and missed at the top level of a file.
- TS/JS's `no-unused-vars` counts parameters only.
- Unused variables and imports stay with the project's linter, which already reports them.
- Swift's `debug_output` rule finds 4 calls: `print` · `debugPrint` · `NSLog` · `dump`.
- Swift's `globals` rule finds a `var` at file level, `main.swift` aside.
- Swift's `bool_params` rule finds an unlabeled `_ flag: Bool`.
- A function handed to a call is the callee's choice and doesn't count for `bool_params`.
- `module-state` is a `let` or `var` at module level that a function assigns.
- Go's `globals` is a package variable that a function assigns with `=`, an operator such as `+=`, `++` or `--`. A variable no function assigns is a table or a setting, and stays quiet. So do what `init` assigns, another package's variable that `main` assigns, a write to a field or an element, and a method call such as an atomic counter's `Add`. The variables come from every file of the package in the folder, and the finding marks each function's first assignment.
- Go's `debug_output` is a call of `print` or `println`, or of `fmt.Print`, `fmt.Printf` or `fmt.Println` outside a `package main` program's own files. A print in a test file counts, and one in an `Example…` function doesn't.
- Go's `type_escape` is a type assertion with one result, `x.(T)`, which panics on the wrong type. The comma-ok form checks it, `v, _ := x.(T)` among them. `any` doesn't count, since Go checks it at each use.
- A setter takes a boolean for what its name says, so it doesn't count for `bool_params`: `set` or `set_…` in Python and Rust, `set` alone or before a capital in Go, TS/JS and Swift, and a TS/JS `set x(v)` accessor. Each name is read from the language's tree.
- A Go function that assigns a variable of an imported package, as in `pkg.Default = v`, counts for `globals` in its own file. A local value's field and a field of the package's variable don't. In `main` and `init` it is the program's setup, as `flag.Usage = usage`, and doesn't count.
- `magic_numbers` leaves out -1, 0, 1 and 2 in Go, TS/JS and Rust, so `n / 2` counts nowhere and `n * 100` does. Python's rule reads comparisons alone, and Swift's runs only where the project's SwiftLint config turns it on.
- Go's `broad_test_asserts` is a testify `Error` or `Panics` in a test file, which any error passes.
- Swift's `broad_test_asserts` is an `XCTAssertThrowsError` with no handler, or an `#expect` or `#require` that any `Error` passes.
- Swift's `deprecated_api` comes from type-checking the changed files of a SwiftPM package, so an Xcode project is left out.

Rust gets 9 of these from clippy and rustc: `suppression` · `swallowed_error` · `unused_params` · `debug_output` · `todo` · `type_escape` · `bool_params` · `deprecated_api` · `missing_docs`. broom reads 5 more from its syntax tree: `magic_numbers` · `commented_code` · `globals` · `broad_test_asserts` · `broad_catch`. A Rust global is a `static mut`, a `static` that holds a lock, a cell or an atomic, or a `thread_local!`, and a plain `static` is a constant. A broad test assertion is a `#[should_panic]` with no `expected`, or an `assert!` that any `Err` passes. Its `skipped_test` is an `#[ignore]`, read by broom. Its `swallowed_error` is a `Result` dropped with `let _ =`, and it is a nit, since that can be deliberate. Its `todo` is a `todo!()` or an `unimplemented!()`. Test code is not built, so a test may be long, unwrap and print. CSS, SCSS and Less have no smell tool.

The five `broom/` rules need Node. Without it only these smells go unmeasured, and a note says so.

- **Why**:
  - [009: An occurrence counts when the change raises the count](../specs/decisions/009-occurrence-by-count.md)
  - [042: A Go rule flags what its message says](../specs/decisions/042-go-rules-flag-their-message.md)

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

TS/JS can't catch by type, so there a handler has to look at what it caught. An empty `catch` is a `swallowed_error`. Swift's `try?` drops every error too, and it is left out, since it is the language's common way to say an error doesn't matter. Go's deliberate `_ = recover()` under a comment that says why is the same tree as a careless one, so it passes accepted with a reason.

---

### F4.2.2: Skipped test

`skipped_test` is a test a change marks as skipped or disabled. It is the shortest way to make a failing suite pass. A change that adds one gets a hint.

It covers Python, TS/JS, Go, Rust and Swift, and broom reads it from the test files' syntax trees, so a skip written inside a string doesn't count. A skip that a condition decides doesn't count, such as `skipUnless` or a `t.Skip` under an `if`. That is how a suite fits the machine it runs on. `broom stats` and the check-up still count those.

---

### F4.2.3: Untested file

`untested_file` is a code file a change adds with no test file named for it anywhere in the repo, such as `foo.py` with no `test_foo.py`. A change that adds one gets a nit. It needs no tool.

A file of fewer than 30 code lines is left alone. So are `__init__.py` and `conftest.py`.

A Rust file is tested when it holds a `#[test]` or a `#[cfg(test)]`, or when a file such as `tests/<name>.rs` is named for it. `main.rs`, `lib.rs`, `mod.rs` and `build.rs` are left alone.

2 gaps:

- The pairing goes by file name, so a test named otherwise is missed.
- CSS takes no part, since it has no such naming.

---

## F4.3: Duplicate code

A new duplicate block with a side in the change's files hints past 10 lines and blocks past 30. It is found anywhere in the repo, and compared with the base so old copies stay quiet.

4 kinds of clone don't count:

- Clones of a linked worktree that sits inside the repo, whose files are the repo's own.
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

A test is judged by what it proves, not by how it reads. In a test file only 4 smells keep their level, since each lets a test pass while the code is wrong:

| Smell | Level | How it lets a test lie |
|---|---|---|
| `skipped_test` | hint | the test never runs |
| `broad_test_asserts` | hint | any error passes it |
| `swallowed_error` | block | the failure is caught and dropped |
| `suppression` | block | a rule the project set is silenced |

Every other smell in a test file is a nit: told, and it stops nothing. That holds past the hard limit too, and for an old smell in a test the change touches. The project's own linter and type checker judge tests as they judge code.

In tests, complexity and magic numbers don't count at all. Neither do the length or complexity of `describe`, `it` and `test` callbacks.

A test file may be twice as long as a code file before its length is told: its `file_lines` limits are 800 and 2000. `test_limits` in `.broom.json` moves the limits for test files.

A test file is told by its path. Besides the names a test runner collects, the helpers a runner names are test code:

- **A Go test-helper package**: a Go file directly in a folder whose name ends in `test`, such as `httptest` or `cachetest`. Go names a package after its folder, and the name says it serves tests.
- **pytest's `conftest.py`**: pytest loads it only for tests.
- **Jest's and Vitest's helpers**: a file under `__mocks__/`, and the setup files `setupTests.*`, `jest.setup.*` and `vitest.setup.*`.

1 gap:

- A Go folder named `latest`, `attest` or `contest` reads as test code.

- **Stance**: [Whether it can lie, not how it reads](../PHILOSOPHY.md#what-does-broom-judge-in-a-test)
- **Why**:
  - [051: A test is judged by what it proves, not by how it reads](../specs/decisions/051-tests-judged-by-what-they-prove.md)
  - [012: Tests take limits of their own](../specs/decisions/012-test-limits.md)
  - [040: A test file may be twice as long as a code file](../specs/decisions/040-test-file-length.md)
  - [045: A Go test-helper package is test code](../specs/decisions/045-test-helper-packages.md)

---

## F4.8: Limits told before the work

At the start of a session in a repo with code, Claude is told the bar in a few lines: how long a function and a file may be, how many parameters, how deep the nesting and how high the complexity, each with the size past which a change is blocked. A limit that differs for test files is named beside the code's, such as how long a test file may be, and the card says that in test files only a skipped test, a broad assertion, a swallowed error and a suppression stop a change. It says that a length counts code lines, so comment lines and blank lines are free. It also names what blocks for being added, how a blocked finding passes and which broom command answers a question about the repo.

The numbers are the repo's own, so limits moved in `.broom.json` show, and a smell the repo turned off is left out. A repo with no code, or with `smells` off, gets no card. It is told once per session.

- **How it works**: [Setup](../specs/setup.md)

---

## F4.9: Old smells in touched code

When a change touches a function, a type or a file that already holds a sized smell, Claude is told to clean it in the same change. The finding says `you touched it, clean it up in this change`, so it reads apart from a smell the change made worse. It is a hint: it stops a commit and a turn's end, and passes with a reason.

A function or a type is touched when a changed code line lies inside it. A file is touched when it gained code lines besides imports. A comment line or a blank line that a change adds or edits touches nothing. Code the change doesn't touch stays quiet, and so does a file that was only renamed.

A function, a type or a file that was already past the hard limit and that the change grew can't be accepted. The block marks that line, and `broom known --accept` leaves it out and says what size to bring it back to. A smell that is newly past the hard limit can be accepted as before.

2 gaps:

- Outside Python a touched function is told its length only, since the tools give no range for the other sized smells.
- A touched Go type isn't told, since its methods lie apart in the file.

In Rust a touched function that is too long is told.

- **Stance**: [Clean as you go](../PHILOSOPHY.md#when-is-a-smell-cleaned)
- **How it works**: [Smells](../specs/smells.md)
- **Why**: [028: A change is told the old smells in the code it touches](../specs/decisions/028-old-smells-in-touched-code.md)
