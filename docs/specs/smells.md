# Smells

This part measures code smells in what a change touches and says which of them the change made worse. It exists so that one bar holds in every repo, apart from each project's lint config.

```
changed files ─┬─▶ scratch copy, as they are ─┐
               ├─▶ scratch copy, at the base ─┼─▶ compare ─▶ worse? ─▶ hint or block
               ├─▶ real tree (typed tools, import graphs) ─▶ on an added line? ─┘
               └─▶ whole repo (jscpd: clones, dead code) ─▶ new, with a side in the change?
```

---

## The scratch copy

Each tool runs alone in a scratch copy of the files under a config broom writes, so the project's lint config can't move the bar. It runs once on the files as they are and once on them at the base revision, which is HEAD for hooks. The base versions are read with one `git cat-file --batch`.

Findings match across the two versions by file, metric and the function's name, else the text of the line.

What the measurers found in a file is kept by its content, the limits, the tools and broom's version, with no expiry, the newest 20,000 entries, so the base of a change and a file still blocked aren't measured twice. A tool that moved or went missing gets its files measured again. Only a measurement that finished whole is kept.

- [005: Smells are measured by broom's limits in a scratch copy](decisions/005-own-bar-scratch-copy.md)

---

## Code lines

A length is a count of code lines: a file's, a function's or a type's. A code line holds something besides space outside a comment. Each measurement reads the code lines of its files once, and every length is counted from that set.

The comments come from the file's syntax tree. Python's are the comment tokens of `tokenize` and the docstrings `ast` names: the string a module, a class or a function opens with. Swift's are SourceKit's comment tokens. Go's, TS/JS's, Rust's and CSS's are the comment nodes that ast-grep's rules in `all-comments.yml` match. The bytes of each comment are blanked, and a line with something left on it is a code line.

Past a point Python's tokenizer can't read, every line that isn't blank counts. Without ast-grep, or without SourceKit for Swift, the same holds for the whole file, with the tool's note.

5 sources give the lines a function or a type takes:

- **Python**: `ast` gives a function's and a class's first and last line.
- **TS/JS**: oxlint's length rule leaves comments and blank lines out and labels the function. broom's own rule labels a class. broom counts the code lines under each label.
- **Go**: ast-grep gives each function and method declaration, and each type with its methods. No linter measures a Go length.
- **Rust**: ast-grep gives each type with its `impl` blocks. clippy counts a function's body itself.
- **Swift**: SwiftLint counts a function's and a type's body itself.

A row keeps the lines its function or type takes beside its length. clippy and SwiftLint give a length and no span, so a Rust function's span comes from ast-grep's tree and a Swift function's from the compiler's.

- [039: A length counts code lines](decisions/039-code-lines.md)

---

## Made worse

A sized smell counts when the change pushed it past a limit, or grew it while past the hard one. Growth between the limits is left alone.

A file git sees as renamed is read at its old path, and its changed lines come from a rename-aware diff. A long file whose code lines besides imports didn't grow isn't longer for the change.

An occurrence smell counts when the change raises the count in a file. Lines match the base by text: a moved line stays old, and an edited line that keeps its occurrence adds nothing. A line counts once per smell.

Where a smell is found by a guess and not a parse, it is a nit even when the same smell blocks in another language.

---

## Touched

A sized smell that was already past its soft limit at the base, and that the change didn't make worse, is a hint when a changed code line lies in its unit. A comment line or a blank line that the change added or edited touches nothing. A function or a type runs from the row's line through the lines it takes. Where its tool gives no span, it runs through its length, which is shorter. A file counts when it gained code lines besides imports. In Python `ast` gives each function's range, so parameters, nesting, complexity and a nested ternary are told too. The other languages' tools give no range for those four, so there they stay untold. A Go type's methods lie apart in its file, so its first line and its size give no range, and it stays untold as well. No tool runs for this: it reuses the rows of both versions.

A sized smell that was past the hard limit at the base and grew carries the size it had. That mark travels with the blocked result, and accepting leaves such a finding out.

- [006: A smell counts when the change pushed it past a limit](decisions/006-made-worse.md)
- [007: A renamed file is measured against its old path](decisions/007-renames-and-imports.md)
- [009: An occurrence counts when the change raises the count](decisions/009-occurrence-by-count.md)
- [028: A change is told the old smells in the code it touches](decisions/028-old-smells-in-touched-code.md)

---

## The real tree

A typed linter or a module graph can't work on the scratch copy, whose imports don't resolve. Those tools run in the project's own checkout: Go's typed linters, TS/JS import cycles, dependency-cruiser and clippy. Go's package variables are read there too, since a package declares them in files a change may not touch. With no copy of the base to compare with, a finding counts when it is on a line the change added, a new file included. git takes a line that only moved for an added one, so an occurrence on an added line whose text the file already held at the base stays old, as often as the base held it.

Go's scratch copy runs only linters that read syntax alone, so Go's repeated literals stay unmeasured. One linter that needs types makes golangci-lint skip every linter in the run.

clippy runs with thresholds from a `clippy.toml` of broom's own, under a config path and a target directory of its own, so it and the project's clippy run don't make cargo check the crate again each time. A crate is checked whole, in one run.

clippy runs with rustc's `missing_docs` lint turned on too, which is off by default.

clippy takes one threshold per lint, so it gets the soft limit, and the size in its message says whether the finding is a hint or a block. Its nesting lint names no depth, so that smell only hints. rustc's own warnings give dead code and unused parameters, the latter kept only where the unused variable sits in a function's parameter list. `cargo clippy` builds no test code, so tests are left out.

A deprecated call needs types in Go, TS/JS, Rust and Swift, so it is found here too: by staticcheck's `SA1019` in the Go run, by rustc's `deprecated` lint in the clippy run, by oxlint's `typescript/no-deprecated` in the run that finds import cycles, and by the Swift compiler's `DeprecatedDeclaration` warnings. Swift's changed files are type-checked as the primary files of their target, which `swift package dump-package` names into a scratch path of broom's own, so the package is never built. A call into another module resolves only when a build left that module in the package's `.build`. That oxlint run is type-aware only where tsgolint is installed. Python's come from ruff in the scratch copy, where an alias imported from `typing` is dropped. The finding keeps the tool's own words, since they name what replaced the API.

The session scan gives these tools 20 seconds between them. The quick ones go first and clippy last, and a tool the time runs out before is skipped with a note. `broom smells` from the command line has no such limit.

- [015: Tools that need types run in the project's checkout](decisions/015-real-tree-for-typed-tools.md)

---

## Cycles

A Python import closes a cycle when what it imports leads back to its file. broom reads the module-level imports itself. An import inside a function, or under `if TYPE_CHECKING:`, is how code breaks a cycle, so it doesn't count. Names are matched by their path, and a name two files share is skipped.

Rust's `use` declarations of the same crate are read from the syntax tree: `crate::`, `super::` and `self::` paths, grouped or not, each mapped to its `x.rs` or `x/mod.rs`. `#[path]`, inline `mod` blocks, `src/bin/` and test code aren't read. The graph is Python's, so the same rules of a cycle hold.

A folder cycle is an import that leads into a folder whose files lead back to this one. Python's and Rust's are read by broom, and `src/a.rs` belongs to the folder `src/a/` where that folder exists. TS/JS's are read by dependency-cruiser, package by package from the nearest `package.json`, runtime imports only. It loads the TypeScript that sits beside it, needs one below 7 and reads no `.ts` file without one, silently.

So broom picks the dependency-cruiser to run. Its own copy comes first: one installed under broom's data directory with a TypeScript 6 beside it, which reads a project whatever TypeScript the project uses. Without that copy it takes the project's or the PATH's, unless the repo holds TypeScript files and the TypeScript beside that one is 7 or later, or missing. Which TypeScript sits beside a copy is read from the `package.json` files Node would search, with no process started. A changed file that dependency-cruiser still didn't read is said so in a note.

- [036: broom keeps its own dependency-cruiser](decisions/036-own-dependency-cruiser.md)
- [014: No layering rules without a project's own](decisions/014-no-layering-rules.md)

---

## broom's own oxlint rules

Six rules of broom's own are loaded as an oxlint JS plugin, an alpha feature, in a second oxlint pass. They need Node. Without it, or with an oxlint that can't load plugins, only these smells go unmeasured, and a note says so. A test loads the plugin with the oxlint installed, so an upgrade that breaks it shows up there. It was tested with oxlint 1.85 and Node 24.

The commented-code rule guesses: a comment that compiles as JS and has code's punctuation, with `Note: x()` skipped as a label. TypeScript syntax in a comment doesn't compile, so it is missed.

The broad-catch rule keeps the handlers it is inside of on a stack: a `catch` clause, or a function handed first to a `.catch()` call. Each mention of a handler's parameter counts for it, and a `throw` marks every open handler. A handler that closes with no mention beyond the parameter itself and no `throw` is reported, unless it is a `catch` with an empty body, which oxlint's own `no-empty` owns.

oxlint's own rule list, read in full in 2026-11, has nothing for the first five smells, bar Jest's `require-to-throw-message`. For the broad catch only its rules named for `catch` were looked at, on 2026-11-19 with oxlint 1.85.

---

## Syntax trees

What no linter covers is read from the file's syntax tree, never from a pattern of its text. A string, a comment or a raw string that looks like code is never taken for it, and a call split over several lines is read like one on a line.

The tree comes from 3 places:

- **Python**: the standard library's `ast` and `tokenize`, in broom's own process.
- **Swift**: the compiler's `-dump-parse` with JSON output, which gives the statements and declarations, and SourceKit, the toolchain's own reader, which gives the tokens, the comments and each call's place. SourceKit is loaded from the toolchain with `ctypes` and answers from a service of its own, so a crash there loses an answer and not the hook. One swiftc run reads up to 200 files.
- **Go, Rust, TS/JS and CSS**: ast-grep, with the YAML rules under `defaults/sg/rules/`. Each rule names the smell it finds, and a run applies only the rules its check needs. SCSS and Less are read with the CSS grammar.

Code a parser can't read is left out, with a note: Swift's declaration that holds the error, and in the languages ast-grep reads the region its grammar marks as an error. Without ast-grep the smells it reads go unmeasured, with a note, and nothing blocks.

A generated file is one whose comment on one of its first 5 lines says `DO NOT EDIT` or `@generated`. A file grew by imports alone when only its import declarations grew. A TS/JS function passed to `describe`, `it` or `test` is a container, and its length and complexity don't count. Each of these is read from the tree too.

Commented-out code is decided by the language's own parser: a comment, or a run of whole-line comments, counts when its text parses as code with no error and holds a statement, a declaration, a call or an assignment. Prose that happens to parse still counts, so it stays a nit.

A Go type's length is its declaration plus every method on it in the same file, matched by the receiver's type, in a `type ( ... )` group too. A Rust type's length is its item plus its `impl` blocks in the same file. Rust's test code is a file under `tests/`, a file named for tests, or an item under `#[cfg(test)]` or marked as a test.

A Go package variable that a function assigns is read from every file in the folder of a changed Go file, grouped by the name in each file's package clause. The package's variables come from all of them, and the assignments from the changed files, one row per function and variable at its first assignment. What `init` assigns, another package's variable that `main` assigns and a name the function declares itself are left out. A Go print in a `package main` file that is no test is the program's output, so only the print builtins count there.

- [038: Smells are read from a syntax tree](decisions/038-syntax-trees.md)
- [042: A Go rule flags what its message says](decisions/042-go-rules-flag-their-message.md)

---

## Duplicate and dead code

jscpd 5 scans every code file in the repo, and a clone's size is the code lines of the side measured. Given the base ref it scans that tree too and marks the clones the base lacked. A clone counts when it is new and has a side in the change's files. jscpd gets a baseline only from a base git can resolve.

Dead code comes from the same tool in TS/JS and Python, with tests and entry points left out, from golangci-lint's `unused` in Go, from rustc in Rust and from Swift's tree, where a `private` or `fileprivate` declaration no other token of its file names is dead. A finding counts on a line the change added, or in a new file. Generated code still counts as using code.

- [010: Duplicate code is found across the whole repo](decisions/010-whole-repo-clones.md)
- [011: Code marked legacy may be repeated](decisions/011-legacy.md)
- [013: Dead code counts on added lines](decisions/013-dead-code-added-lines.md)

---

## Tests

Two smells are read from the files' syntax trees with no linter. A skipped test is found by each language's own form in a test file's tree, and it counts like any occurrence: when the change raises the count. A skip whose name states a condition, that sits behind an `if`, a `case` or a `catch`, or that Rust puts under `cfg_attr`, is how a suite fits its machine, so it is left out.

A new code file counts as untested when no test file anywhere in the repo is named for it. A Rust file also counts as tested when it holds its own tests. The names of all files come from one `git ls-files`, and it runs only when the change adds a code file of 30 code lines or more.

A test file is told by its path: a name a test runner collects, such as `test_a.py`, `a_test.go`, `a.test.ts` or a file under `tests/`, a Go file directly in a folder whose name ends in `test`, such as `httptest`, pytest's `conftest.py`, and Jest's and Vitest's helpers: a file under `__mocks__/` and the setup files `setupTests.*`, `jest.setup.*` and `vitest.setup.*`. Go names a package after its folder, so the folder's name is the package's. A test file's limits are the code's with `file_lines` doubled, and then what `test_limits` sets. The tools measure against the lower soft limit of the two sets, and each row takes its level from the limits of its own file.

A row in a test file then keeps its level only for `skipped_test`, `broad_test_asserts`, `swallowed_error` and `suppression`. Every other row there becomes a nit, a touched one and one past the hard limit among them. The level is set once, where the row is made, so the commit check, the turn's end, the scans and the hotspots all read the same level.

- [051: A test is judged by what it proves, not by how it reads](decisions/051-tests-judged-by-what-they-prove.md)
- [009: An occurrence counts when the change raises the count](decisions/009-occurrence-by-count.md)
- [012: Tests take limits of their own](decisions/012-test-limits.md)
- [040: A test file may be twice as long as a code file](decisions/040-test-file-length.md)
- [045: A Go test-helper package is test code](decisions/045-test-helper-packages.md)

---

## What is skipped

Paths are judged by directory name before any file is read. Dependencies, environments, build output, generated code, fixtures, minified files and `.d.ts` are skipped. `build`, `out`, `release` and `target` are skipped only where git doesn't track the files. Tracked directories skipped by name are listed in a note.

- [008: Build-output names skip only untracked files](decisions/008-tracked-build-names.md)
