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

What the measurers found in a file is kept by its content for a day, so the base of a change and a file still blocked aren't measured twice. A tool that moved or went missing gets its files measured again. Only a measurement that finished whole is kept.

- [005: Smells are measured by broom's limits in a scratch copy](decisions/005-own-bar-scratch-copy.md)

---

## Made worse

A sized smell counts when the change pushed it past a limit, or grew it while past the hard one. Growth between the limits is left alone.

A file git sees as renamed is read at its old path, and its changed lines come from a rename-aware diff. A long file whose lines besides imports didn't grow isn't longer for the change.

An occurrence smell counts when the change raises the count in a file. Lines match the base by text: a moved line stays old, and an edited line that keeps its occurrence adds nothing. A line counts once per smell.

Where a smell is found by a guess and not a parse, it is a nit even when the same smell blocks in another language.

---

## Touched

A sized smell that was already past its soft limit at the base, and that the change didn't make worse, is a hint when a changed line lies in its unit. A function or a type runs from the row's line through its length. A file counts when it gained lines besides imports. In Python `ast` gives each function's range, so parameters, nesting, complexity and a nested ternary are told too. The other languages' tools give no range for those four, so there they stay untold. A Go type's methods lie apart in its file, so its first line and its size give no range, and it stays untold as well. No tool runs for this: it reuses the rows of both versions.

A sized smell that was past the hard limit at the base and grew carries the size it had. That mark travels with the blocked result, and accepting leaves such a finding out.

- [006: A smell counts when the change pushed it past a limit](decisions/006-made-worse.md)
- [007: A renamed file is measured against its old path](decisions/007-renames-and-imports.md)
- [009: An occurrence counts when the change raises the count](decisions/009-occurrence-by-count.md)
- [028: A change is told the old smells in the code it touches](decisions/028-old-smells-in-touched-code.md)

---

## The real tree

A typed linter or a module graph can't work on the scratch copy, whose imports don't resolve. Those tools run in the project's own checkout: Go's typed linters, TS/JS import cycles, dependency-cruiser and clippy. With no copy of the base to compare with, a finding counts when it is on a line the change added, a new file included.

Go's scratch copy runs only linters that read syntax alone, so Go's repeated literals stay unmeasured. One linter that needs types makes golangci-lint skip every linter in the run.

clippy runs with thresholds from a `clippy.toml` of broom's own, under a config path and a target directory of its own, so it and the project's clippy run don't make cargo check the crate again each time. A crate is checked whole, in one run.

clippy takes one threshold per lint, so it gets the soft limit, and the size in its message says whether the finding is a hint or a block. Its nesting lint names no depth, so that smell only hints. rustc's own warnings give dead code and unused parameters, the latter kept only where the unused variable sits in a function's parameter list. `cargo clippy` builds no test code, so tests are left out.

A deprecated call needs types in Go, TS/JS and Rust, so it is found here too: by staticcheck's `SA1019` in the Go run, by rustc's `deprecated` lint in the clippy run, and by oxlint's `typescript/no-deprecated` in the run that finds import cycles. That oxlint run is type-aware only where tsgolint is installed. Python's come from ruff in the scratch copy, where an alias imported from `typing` is dropped. The finding keeps the tool's own words, since they name what replaced the API.

The session scan gives these tools 20 seconds between them. The quick ones go first and clippy last, and a tool the time runs out before is skipped with a note. `broom smells` from the command line has no such limit.

- [015: Tools that need types run in the project's checkout](decisions/015-real-tree-for-typed-tools.md)

---

## Cycles

A Python import closes a cycle when what it imports leads back to its file. broom reads the module-level imports itself. An import inside a function, or under `if TYPE_CHECKING:`, is how code breaks a cycle, so it doesn't count. Names are matched by their path, and a name two files share is skipped.

A folder cycle is an import that leads into a folder whose files lead back to this one. Python's are read by broom. TS/JS's are read by dependency-cruiser, package by package from the nearest `package.json`, runtime imports only. It loads the TypeScript that sits beside it, needs one below 7 and reads no `.ts` file without one, silently.

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

## Go's text reads

golangci-lint has no linter for three of Go's smells, so broom reads them from the source in the scratch copy, with no tool. gofmt's layout makes the text enough: a declaration starts at the first column, and the brace that closes it stands there too.

A type's length is its `struct` or `interface` declaration plus every method on it in the same file, matched by the receiver's type. A type inside a `type ( ... )` group isn't read, and a raw string that holds a brace at the first column ends a block early.

A broad catch is a `recover()` that stands as a statement or is assigned to `_`. A broad test assertion is a testify `Error` or `Panics` in a `_test.go` file, called on `assert`, `require`, `Assert()` or `Require()`. `s.Error(` is left out, since that name reports a failure on a `*testing.T`.

---

## Duplicate and dead code

jscpd 5 scans every code file in the repo. Given the base ref it scans that tree too and marks the clones the base lacked. A clone counts when it is new and has a side in the change's files. jscpd gets a baseline only from a base git can resolve.

Dead code comes from the same tool in TS/JS and Python, with tests and entry points left out, and from golangci-lint's `unused` in Go. A finding counts on a line the change added, or in a new file. Generated code still counts as using code.

- [010: Duplicate code is found across the whole repo](decisions/010-whole-repo-clones.md)
- [011: Code marked legacy may be repeated](decisions/011-legacy.md)
- [013: Dead code counts on added lines](decisions/013-dead-code-added-lines.md)

---

## Tests

Two smells are read from the files with no tool. A skipped test is found by each language's own form in the text of a test file, and it counts like any occurrence: when the change raises the count. A skip whose name states a condition, or that sits behind an `if`, is how a suite fits its machine, so it is left out.

A new code file counts as untested when no test file anywhere in the repo is named for it. The names of all files come from one `git ls-files`, and it runs only when the change adds a code file of 30 lines or more.

- [009: An occurrence counts when the change raises the count](decisions/009-occurrence-by-count.md)

---

## What is skipped

Paths are judged by directory name before any file is read. Dependencies, environments, build output, generated code, fixtures, minified files and `.d.ts` are skipped. `build`, `out`, `release` and `target` are skipped only where git doesn't track the files. Tracked directories skipped by name are listed in a note.

- [008: Build-output names skip only untracked files](decisions/008-tracked-build-names.md)
- [012: Tests take limits of their own](decisions/012-test-limits.md)
