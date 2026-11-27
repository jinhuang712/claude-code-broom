# Changelog

---

## Unreleased

---

## 0.30.2 — 2026-11-27

---

### What a real Go repo met

- A Go error dropped with `_` is no smell again. Most of what 0.30.1 flagged was cleanup, such as `_ = x.Close()`, or an encode, such as `_ = json.Marshal(v)`: the form errcheck itself asks for.
- A Go `main` that assigns another package's variable, as in `flag.Usage = usage`, sets the program up and doesn't count for `globals`, as `init` didn't.
- Go's magic numbers leave out -1, 0, 1 and 2, as TS/JS and Rust do, so `n / 2` counts in no language.
- Nits are counted apart from hints: `0 past the hard limit, 6 hints, 238 nits`. Before, a nit read as a hint in every total.
- A nit weighs nothing in a hotspot's score, and a file of nits alone is no hotspot.
- `broom smells --json` gives each smell's `lines`, every line it stands on, where `text` cuts the list short.
- The `tests_not_run` fix line says that a runner of the project's own is seen only once `test_commands` names it, where the repo names none.

---

### The record

- A commit or a turn's end that covers a file closes the open findings another turn, another session or a worktree left there, once they are gone. Before, a fix made elsewhere stayed open in the record and lowered the fix rate.
- A test run counts for the whole session, so work tested in a worktree at one turn counts as tested when a later turn lands it.
- A known issue accepted before 0.28.1 in a worktree since deleted moves to the main checkout's file once a line of that file proves it, where before it read as changed.

---

## 0.30.1 — 2026-11-27

---

### Sharper rules

- A setter's boolean is no flag in Python, Rust, TS/JS and Swift either: `set_enabled(self, enabled: bool)`, `setEnabled(enabled)` and a `set x(v)` accessor. Before, only Go's setters were left out of `bool_params`.
- Jest's and Vitest's helpers are test code: a file under `__mocks__/`, and `setupTests.*`, `jest.setup.*` and `vitest.setup.*`.
- A Go function that assigns another package's variable, as in `pkg.Default = v`, counts for `globals`.
- A file Claude edited that git ignores is left out of the turn's end, where before it could block it.
- `broom known` marks an entry whose code changed, as `(its code changed: no longer matches)`, and drops none.
- A Swift and a Rust function carry the lines they take, so an old long function touched near its end is told.
- A repeated block's size counts code lines, so a block of comments and blank lines is no clone.

---

### More rot

- A Go error dropped with `_`, as in `_ = f()`, is a `swallowed_error` nit, found by golangci-lint's `errcheck`.
- The check-up counts unsafe code, type escapes and broken Markdown links, and `broom stats` shows the unsafe code and the broken links.
- A lint suppression in a YAML, shell or HTML comment counts in the suppressions and as a self-waiver.
- `broom stats` lists the largest tracked files of any kind.

---

## 0.30.0 — 2026-11-27

---

### Open findings come back

- A finding that stopped a commit or a turn's end and that no fix or accept has ended is told to Claude again: at the prompt that holds the user's answer to a question about it, and at a session's start in its repo. Before, it left Claude's sight once the turns moved to other files.
- Before a session's start tells, broom checks the findings' files again: one gone is recorded as fixed and not told. At the answer it tells at once and checks right after.
- It tells and never blocks. A prompt with no question waiting costs one shell start, about 10 ms, and no Python.
- A block line of the ledger holds the finding's line and the hash of its text.

---

## 0.29.0 — 2026-11-27

---

### No clock

- No rule of broom turns on the clock any more. Only broom's own running time keeps a bound. A test lists every reading of the clock and what it is for.
- A check that ran out of time is skipped until the repo's HEAD moves. Before, it was skipped for 20 minutes.
- The turn's end waits once for each piece of background work, by its task id, and a prompt during the wait keeps the waiting turn's changes, Bash's too. Before, the wait ended after half an hour.
- Content that passed and what the measurers found are kept while the content, broom's version and the repo's `.broom.json` stay the same, the newest 20,000. Before, they were kept for a day.
- Hotspots and `broom stats`' history count the last 500 commits, and `--days` of `broom diagnose` and `broom stats` is now `--commits`. Before, they counted 90 days.
- The check-up counts TODO comments, and `broom stats` gives no TODO ages. Before, it counted those older than 180 days.
- A coverage report is behind when a code file it covers was written after it. Before, it gave its age in days and compared it with the last commit.
- `broom report` reads the whole record, and `--since` takes a version of broom such as `0.29.0`. `--days` is gone. Every ledger line holds the version that wrote it.
- The ledger is trimmed by size alone, and the session folders, claims and the tools' caches by count.

---

### Collapsed

- What Claude hides still counts. `broom smells`, `broom diagnose` and `broom sweep` count the findings accepted as known in their totals and say how many are collapsed, where before they left them out. `broom smells --json` gives `open` beside `known`.
- After `broom smells --dismiss` the session note gives its count in one line and asks for no cleanup, where before it vanished.
- A commit check or a turn's end that has something to say adds how many known issues in its files it collapsed.

---

## 0.28.5 — 2026-11-27

---

### Smells

- A Go file in a folder whose name ends in `test`, such as `httptest`, is test code: a test-helper package. Its file may be twice as long, and its complexity, magic numbers and missing doc comments don't count, as in a `_test.go` file. Before, it was measured as library code.
- pytest's `conftest.py` is test code wherever it lies, where before only one under `tests/` was.
- Go's `broad_test_asserts` counts in every test file, a helper package and a file under `tests/` among them, where it counted in `_test.go` files alone.

---

### Known issues

- A known issue never expires. It stays known until its code changes or `broom known --clear` removes it. Before, it expired after 30 days, a limit no decision had chosen, and only once the next accept was written.
- `broom known --accept "<why>" --agreed --smell KIND FILE[:LINE]` accepts a smell that stands in code no change touches, once the user agreed it stays. Before, only what a block showed could be accepted, so `broom smells` listed such a smell for good.
- `broom smells`, `broom diagnose` and the session note leave an accepted smell out and say how many they left out. It comes back when its line changes, or when a sized smell's size changes.
- `broom known` marks an accept the user agreed to with `the user agreed` beside its reason.

---

### Record

- A finding put to the user with `--ask` that no later check found gone, and that wasn't accepted, counts against its rule's fix rate. Before, it counted against no rule, so a rule that was mostly noise read as fixed every time.
- It stays among the open findings, marked as asked, as `38 (asked 36)`, and is never shown as let through.

---

## 0.28.4 — 2026-11-26

---

### Smells

- Go's `globals` counts a package variable that a function assigns, as its message says. Before, every package variable counted, a lookup table and a table of test cases among them. What `init` assigns, a write to a field or an element and a method call such as an atomic counter's `Add` stay quiet. The variables come from every file of the package, so a test that assigns a variable of another file of its package counts.
- Go's `debug_output` leaves out `fmt.Print`, `fmt.Printf` and `fmt.Println` in a `package main` program, where printing is the program's output, and in an `Example…` function. The `print` and `println` builtins still count everywhere, and so does a print in a library or a test file.
- Go's `type_escape` leaves out the comma-ok assertion `v, _ := x.(T)`, which checks the type and can't panic. The single-value `x.(T)` still counts.
- Go's `bool_params` leaves out a setter: a function named `Set` or `set`, alone or before a capital, such as `SetKeepAlivesEnabled(v bool)`.
- Go's `globals` and `debug_output` are read from the syntax tree with ast-grep, and golangci-lint no longer runs gochecknoglobals or forbidigo. Without ast-grep both go unmeasured, with a note.
- An edited line that keeps its Go print adds nothing, as for every other occurrence smell.

---

## 0.28.3 — 2026-11-26

---

### Sweep

- A commit made before the prompt is not the turn's change, even when the turn brings it in by a pull, a reset or a landing of earlier work. Before, a turn that pulled a remote's commits was blocked for every finding in them.
- What the turn changed is measured from the newest such commit, so a file the turn edits after a pull is judged against what the pull brought.
- A wait for background work that never woke a turn ends at the next prompt after half an hour. Before, that prompt noted nothing, and the next turn's end counted other sessions' commits from the days between as its own.

---

## 0.28.2 — 2026-11-24

---

### Smells

- A length counts code lines: the lines that hold code. Comment lines and blank lines no longer count toward the length of a function, a type or a file, in any language. Before, a change that added only a doc comment to a long file was blocked for growing it. After, it grows nothing.
- A comment line or a blank line that a change adds or edits no longer counts as touching an old smell.
- A Python docstring is a comment, and so is a doc comment in every language.
- The limits stay where they were, so every length reads smaller than before. A length you accepted before is asked once more, since its number changed.
- A finding reads `is 60 code lines long`. Before, it read `is 60 lines long`.
- Go's function length is read by broom from the syntax tree, and funlen no longer runs. It counts from the `func` line through the closing brace. It needs ast-grep: without it a Go function's length goes unmeasured, with a note.
- Without ast-grep, or without SourceKit for Swift, comments can't be told from code in that language. Every line that isn't blank then counts, and a note says so.
- The note at a session's start says that comment lines and blank lines are free.
- A new file counts as `untested_file` from 30 code lines on.
- A test file may be twice as long as a code file: 800 and 2000 code lines where a code file's limits are 400 and 1000. Before, the tests of a code file within its limit were stopped for the cases they list. `test_limits` still moves it, and `{"file_lines": [400, 1000]}` there brings the old bar back.
- The note at a session's start names a limit that differs for test files beside the code's.

---

### Stats

- `broom stats` and `broom diagnose` give a size in the same code lines. Before, they counted every line that wasn't blank. The heading reads `Size (code lines)`.

---

### Docs

- The README shows how broom works in two pictures: the six moments that start it, and what becomes of a finding at a gate. The list of what it does is folded under them.

---

## 0.28.1 — 2026-11-20

---

### Sweep

- A finding accepted in a linked git worktree stays known once the work lands on the main checkout. Before, the turn's end there stopped on it again, and the same reason had to be given twice.
- `broom known` lists such a finding from the worktree and from the main checkout alike, at its place in the main checkout.

---

## 0.28.0 — 2026-11-20

---

### Docs

- The README opens with a picture of what broom covers: the six languages, the 27 smell detectors and what else it does. It follows GitHub's dark or light mode.
- The changelog's sections before 0.18.2 read like the newer ones, in short sentences with no hard wraps.

---

## 0.27.0 — 2026-11-20

---

### Smells

- The checks around the smells read the syntax tree too. A lint suppression is one only in a comment, or in a Rust `allow` attribute, so a marker inside a string on a line you added is no self-waiver. A file is generated when a comment near its top says so, not a string. A file grew by imports alone when only its import declarations grew.
- A TS/JS function passed to `describe`, `it` or `test` is told by the call it is handed to, so a `describe(` inside a string no longer passes for one.
- Go, TS/JS and CSS say where their grammar can't parse a file, as Rust and Swift do, and the smells in that region go unmeasured. Before, they went unmeasured with no word.
- A suppression in a file broom reads no tree for, such as `.vue` or a shell script, is no longer seen.

---

## 0.26.1 — 2026-11-20

---

### Smells

- broom's own TS/JS rule for commented-out code takes only a comment that fails to compile for prose. Before, any error while compiling it read as prose, so a fault of the rule itself passed unseen.

---

## 0.26.0 — 2026-11-20

---

### Smells

- The smells no linter covers are read from each file's syntax tree, never from a pattern of its text. A brace, a `catch` or a `TODO` inside a string, a raw string or a comment is no longer taken for code, and a call split over several lines is read like one on a line.
- Swift's are read by its compiler and SourceKit, which come with the toolchain. Go's, Rust's, TS/JS's and CSS's are read by ast-grep, which `broom doctor` now offers for Go, Rust and TS/JS: `brew install ast-grep`. Without it those smells go unmeasured with a note, and nothing blocks.
- Rust measures all 27 smells: an `if` that gives a value and holds another in a branch is a nested ternary. An `else if` chain is not.
- Swift rules out both cycles, since a Swift file never imports another file. Its 25 smells are the whole bar for it.
- Commented-out code counts when the comment parses as code in its own language. Before, a keyword at its start was enough.
- A Go type declared inside a `type ( … )` group is measured. Before, it was skipped.

---

### Stats and check-up

- Test cases, skipped tests, lint suppressions and TODO comments are counted from the syntax tree in every language, so one written inside a string no longer counts. A Rust `#[allow(…)]` counts as a suppression, and a test ignored under `cfg_attr` counts as one a condition decides.

---

## 0.25.11 — 2026-11-20

---

### Smells

- Swift measures 6 more smells, 25 of 27: nesting, commented-out code, a test assertion any error passes, a `catch` that never reads its error, a call to a deprecated API and a private declaration nothing uses. A deprecated call is found in SwiftPM packages, by type-checking the changed files without a build. `try?` is not a broad catch.
- Rust measures 10 more, 26 of 27: magic numbers, commented-out code, globals, long types, broad test assertions, broad catches, missing doc comments, untested files, and cycles between modules and between folders. A crate's public items now need doc comments, as in Go and Python, and the first check after the update runs clippy over the crate once more.
- Commented-out code is a nit in Swift and Rust, since it is a guess there.

---

## 0.25.10 — 2026-11-20

---

### Record

- `broom report` gives the seconds of a whole check at a commit and at a turn's end, with the smells, beside the seconds per tool. Before, it gave only the seconds per tool, which leave out the smells and say nothing of how long a commit waited. The ledger keeps these seconds from this version on.
- `broom report --all` leaves out repos in a temporary folder, where a test or a trial puts them, and says how many. Before, they counted with your own repos.
- `broom report --since 2026-11-18` starts the period on that day, so a rule's numbers can be read from the day it changed.

---

### Language servers

- Checked in Claude Code 2.1.329: after an edit that adds a type error, Claude sees the diagnostic of broom's server in Go, TS/JS, Rust, Python, Swift and CSS.

---

## 0.25.9 — 2026-11-19

---

### Setup

- `broom doctor` names every enabled plugin whose language server competes with one of broom's, and `/broom:setup` offers to disable it. Before, it named such a plugin only in a repo of that language, so the conflict came up repo by repo.
- A plugin is now judged by the files its language servers claim, not by its name, so a server under an unknown name is caught too.

---

### Version

- `broom --version` and `broom doctor --json` say the version that is installed. 0.25.8 still said 0.25.7.

---

## 0.25.8 — 2026-11-19

---

### Language servers

- The TypeScript language server starts in a project on TypeScript 7. Before, a typescript-language-server installed beside a global TypeScript 7 had no `tsserver` to load, and Claude Code said the server couldn't start.
- broom's own copy now holds a typescript-language-server too, with its TypeScript 6. The command `broom doctor` gives for it installs both, and `/broom:setup` and `/broom:status` run it on your yes. If you installed the copy with 0.25.7, run the command once more.
- Until the copy is installed, a project on TypeScript 7 gets `tsc --lsp`, which gives navigation and no diagnostics.

---

### Smells

- An import that closes a cycle and only moved, because a line above it went or a sort reordered the block, no longer blocks the commit. Before, git showed the moved line as added, and broom took the old cycle for a new one. That blocked a step-by-step cleanup of the cycles.

---

## 0.25.7 — 2026-11-19

---

### TS/JS

- A project on TypeScript 7 gets its cycles between folders checked. Before, dependency-cruiser read none of its `.ts` files and said nothing, and `broom doctor` still called the tool ok.
- broom now keeps a dependency-cruiser of its own, with a TypeScript 6 beside it, under its data directory. `broom doctor` offers it as one command, and `/broom:setup` and `/broom:status` install it on your yes. It changes nothing in your project and leaves your own TypeScript alone. One install serves every repo.
- If you installed dependency-cruiser for broom before, in a project or globally, it is still used where it can read the project.

---

## 0.25.6 — 2026-11-19

---

### git's pre-commit hook

- The line broom gives you for another tool's hook no longer blocks every commit. Before, it called broom at one fixed path, and where that path was missing each commit failed. Now it looks for broom in three places, as broom's own hook does, and lets the commit through when it finds none.
- If you added the old line to a hook, replace it with the line `broom install-hook` prints now.
- `broom doctor` counts the hook as installed once that line is in it. Before, it kept reporting the hook as missing.
- `broom install-hook` never writes over another tool's hook, also when the hook holds broom's line.

---

## 0.25.5 — 2026-11-19

---

### Cleanup

- When broom finds severe smells in a repo, Claude offers to clean them up in its own words. In 0.25.4 it could still tell you to type `/broom:clean`, which is gone.

---

## 0.25.4 — 2026-11-19

---

### Commands

- broom has three commands now: `/broom:setup`, `/broom:status` and `/broom:scan`.
- New: `/broom:scan` runs the tools on a scope you give in your own words and lists what it finds. It fixes nothing and formats nothing. With no scope it scans the whole repo.
- `/broom:status` is about broom alone: which checks run, what it stopped, fixed and let through, and what was accepted with which reason. It no longer measures the code, so it runs no linter. It still offers to set up what is missing on one yes.
- `/broom:sweep` is gone. Before: `/broom:sweep the last 3 commits`. After: `/broom:scan the last 3 commits`, which reports and formats nothing. To have a scope formatted, ask Claude or run `broom sweep`.
- `/broom:clean` is no command any more. Before: `/broom:clean src/api`. After: ask in your own words, such as "clean up src/api", or "fix the first three" after a scan. Claude cleans up the way it did.

---

## 0.25.3 — 2026-11-19

---

### Smells

- Python and TS/JS now measure all 27 smells, and Go measures the 24 the language allows. Go has no ternary to nest, and its compiler refuses import cycles.
- TS/JS: a `catch`, or a function handed to `.catch()`, that never looks at the error it caught and throws nothing is a `broad_catch` hint. Before, only Python had this smell. An empty `catch` is still a swallowed error.
- Go: a type that is too long counts, measured as its declaration plus its methods in the same file.
- Go: a `recover()` whose value is dropped is a `broad_catch` hint.
- Go: a testify `Error` or `Panics` in a test file is a `broad_test_asserts` hint, since any error passes it.
- The three Go smells are read from the source, so they need no tool installed.

---

## 0.25.2 — 2026-11-19

---

### Sweep

- Asking Claude to clean up or refactor code goes to `/broom:clean`. Before, `/broom:sweep` also claimed that request, and a cleanup could end as a lint report.

---

## 0.25.1 — 2026-11-19

---

### Setup

- `/broom:status` tells you where a repo stands and gets it ready in one command. When tools or configs are missing it says what it would install and asks once, then it measures the code and what broom stopped, fixed and let through in the last 7 days, and sums it up with up to three next steps. You type no `broom` command.
- `/broom:setup` says that files are formatted after each edit by default. It said at commit.

---

## 0.25.0 — 2026-11-19

---

### Docs

- The checkpoint of polish and self-test ends, with nothing new in use. Its last fixes shipped in 0.24.1 to 0.24.3, and a fresh session with no tools on its PATH set a Python repo up in one `/broom:setup` run.

---

## 0.24.3 — 2026-11-19

---

### Smells

- A slight smell is called a nit: it is told and stops nothing, as before. Before, `broom smells --json` gave its `level` as `note`, and Claude read `slight code smell(s)`. After, the level is `nit`, and Claude reads `nit(s)`. A note now means only a line that says what a check skipped.

---

### Docs

- The README names the check after an edit and the rule that a turn shows its tests ran, and says that type errors count anywhere.

---

## 0.24.2 — 2026-11-19

---

### Setup

- `broom doctor --checks` names the smells that `smells_off` in `.broom.json` turns off, after the languages. A row of a language still showed them as measured.

---

## 0.24.1 — 2026-11-19

---

### Setup

- `broom doctor` asks for oxlint wherever a repo has TS/JS, since the smell scan needs it whichever linter lints. A project that linted with eslint or biome alone was told all is set while its smells went unmeasured.
- `broom doctor` sees a CSS formatter that a project's config names and that isn't installed, outside a JS project too.

---

### Sweep

- A command added to `test_commands` in `.broom.json` is shown as a self-waiver, since whatever the list names counts as a test run.

---

## 0.24.0 — 2026-11-18

---

### Sweep

- A turn that changed code must show that tests ran. Where a repo has tests, a turn's end stops when no test ran after the last change to code, or when the last test run failed. It passes once the tests ran and passed, by an accept that holds for that turn, or by a question to you. broom runs no test: it knows a test run by its command. `test_commands` in `.broom.json` names a runner broom doesn't know, and `smells_off: ["tests_not_run"]` turns the rule off.
- The note at a session's start tells Claude to run the tests after its last change.

---

## 0.23.5 — 2026-11-18

---

### Sweep

- After each edit broom formats the file and tells Claude what a fast linter finds on the lines that changed: ruff, oxlint or SwiftLint. It never blocks, and it tells a finding once. Before, nothing ran after an edit unless `format_on` was `edit`. After, `format_on` starts at `edit`: set it to `commit` to leave files as written until a commit, and `check_on` to `off` to turn the check off.
- A hint stops a commit. Before, a smell past its soft limit was only told at a commit and blocked the turn's end afterwards, which took one more commit to clean. After, the commit is held back until the smell is fixed or accepted with `broom known --accept "<why>"`.
- Stopping again passes nothing. Before, a turn's end blocked once and a second stop ended the turn with the finding open. After, each stop blocks while a finding is left, and after three blocks broom gives up and tells you in a line that opens `broom GAVE UP`.
- `broom known --ask "<question>"` ends a turn with a question to you about a blocked finding. It passes nothing: the commit stays denied, and your line opens with `WAITS FOR YOUR ANSWER`. Before, the only way to reach you was to be blocked three times.
- `broom known --accept "<why>" --agreed` marks a finding you agreed to leave, and the turn's line shows it apart from what Claude accepted on its own. Three or more of the latter open the line with `Claude ACCEPTED`.
- A turn-end block says which block it is, such as `Block 2 of 3.`
- A slight smell is a note: it is told and stops nothing. The notes are magic numbers, TODO comments, dead code, a new file with no test and any smell a detector guesses.
- The note at a session's start tells Claude the new rule.

---

### Docs

- The docs say what broom is in two halves: a gate the user sets in Claude's flow, and a ruler Claude picks up. broom holds no model, and what needs judgment stays with the coding agent.

---

## 0.23.4 — 2026-11-18

---

### Setup

- `broom doctor --checks` lists what protects a repo: per language, which checks run and with what tool, which don't with the command that turns each on, and where broom has no such check. It also names a missing git hook and what broom checks with no tool installed. `broom doctor --json` holds the same rows under `checks`.
- `/broom:setup` adds the ruff block `broom init` prints for a `pyproject.toml` without ruff settings. Before, the skill didn't say that `broom init` writes nothing there, and a session had to work it out.

---

### Smells

- The note for a missing Node names all five TS/JS smells that go unmeasured. Before, it named three.

---

### Record

- A finding that a commit blocked is remembered until a commit takes its file. Before, a commit of other files made broom forget it, and `broom report` kept showing it as open after it was fixed.
- After a turn ended by stopping again, `broom known --accept` has nothing left to accept. Before, it could pass the same finding a second time.

---

## 0.23.3 — 2026-11-18

---

### Fixes

- git's pre-commit hook checks a commit in a linked worktree as it does in the main checkout. Before, a changed file there was taken for a new one: it got hints meant for new files, under a path without its folders, and duplicate and dead code were looked for in that file's folder alone. A repo used through `git --git-dir` and `--work-tree` had the same fault.

---

## 0.23.2 — 2026-11-18

---

### Record

- A finding that a commit blocked keeps its fix line when the turn's end blocks something else in between. Before, the later block took the earlier one's place, and `broom report` kept showing the first finding as open after it was fixed.
- A finding that a commit and the turn's end both see gone counts as fixed once. Before, it could get two fix lines.

---

### Docs

- The README shows a block message as broom words it today, names the diagnosis and the check-up, and carries the architecture diagram. The Chinese README follows it again.
- The changelog's sections before 0.18.2 are grouped by area.

---

## 0.23.1 — 2026-11-18

---

### Setup

- `broom doctor` finds Python by the `.py` files git tracks, also in a repo with no `pyproject.toml`, `setup.py` or `requirements.txt`. Before, such a repo was told `Languages: none found` and `All set.`, so a missing ruff or a missing git hook was never offered, while its commits were linted all the same.

---

### Check-up

- The line that says a counter grew ends with the command that shows where the number sits, `broom diagnose`. Before, a session that doubted the number counted again by hand and got another one.

---

### Sweep

- The fix line for a skipped test says how a test that must wait passes: it is accepted with what it waits on as the reason. Before, the line said to write that in the skip's reason, and the turn's end blocked all the same.

---

## 0.23.0 — 2026-11-17

---

### Smells

- A dead-code finding says the code is never used outside tests. Before, it said never used, also of a file its own tests import.

---

## 0.22.7 — 2026-11-17

---

### Diagnosis

- A list that `broom diagnose` or `broom compare` cuts short names the command that prints the rest. Before, it pointed at `--json`, which a session then read with a script.

---

## 0.22.6 — 2026-11-17

---

### Check-up

- After an update of broom the check-up takes its numbers as the new baseline without a word. Before, a counter that a new version counts more broadly looked as if it had grown.

---

### Smells

- `missing_docs` covers TS/JS: an exported function or class with no comment above it gets a hint when a change adds it, and the check-up counts them. Any comment counts, JSDoc or not. It needs Node.

---

## 0.22.5 — 2026-11-17

---

### Diagnosis

- `broom smells --only dead_code` lists the code nothing uses. Before, it was refused as an unknown kind.

---

### Record

- A `.broom.json` loosened by a command, such as `sed`, shows in the turn's summary. Before, only a change made with the edit tools did.

---

## 0.22.4 — 2026-11-17

---

### Diagnosis

- `broom smells --only function_lines --top 5` lists the five longest functions in any repo, and `--only type_lines` the longest types. Before, it listed only those past the soft limit. After, the list goes on under the limit, and those are told as sizes and counted as no smell. Rust is left out.
- `broom stats` lists the oldest TODO comments with the day each was written and its age in days. Before, it gave their count per file.

---

## 0.22.3 — 2026-11-17

---

### Fixes

- A commit whose output is redirected is checked. Before, `git commit -m x 2>&1 | tail` and `git commit -m x > /dev/null` passed the commit check unread, and only the turn's end caught what they held. After, they are checked like any commit.
- A commit that takes its message from a heredoc is checked when the message holds an apostrophe. Before, a `git add` in the same command went unseen and the commit passed unread.

---

### Diagnosis

- `broom diagnose` names a language as `broom stats` does, such as TS/JS.
- The fix line for dead code names the case of new code that waits for its caller: it is accepted with that as the reason. Before, the line only said to delete it.
- The note at a session's start says what `broom diagnose` holds: dead code, missing doc comments, calls to deprecated APIs, duplicate tests and unused dependencies.

---

## 0.22.2 — 2026-11-17

---

### Speed

- A turn's end with nothing to check takes about 40 ms, where it took about 100. An edit takes about 30 ms, where it took about 50.

---

### Setup

- `/broom:setup` offers to disable a plugin that serves the same files together with the tools to install. Before, it could ask that as a third question.

---

### Fixes

- A file whose name holds a non-ASCII character is checked like any other. Before, `broom sweep` and the commit check left it out. After, they see it.

---

## 0.22.1 — 2026-11-17

---

### Diagnosis

- `broom smells --only SMELL` keeps one kind of smell, so `broom smells --only function_lines` lists the longest functions first.
- `broom stats` names a language as people do, such as TS/JS, and says how many test files hold test cases when helpers sit in a test folder.
- A TODO in a comment's prose, or in a file's name such as `TODO.md`, no longer counts as a TODO comment. Before, `# every TODO has an owner` counted as one. After, only a marker counts: the word opens the comment, or a colon or a bracket follows it.

---

## 0.22.0 — 2026-11-17

---

### Tests

- `broom stats` and `broom diagnose` show test coverage, read from the report your own test run wrote: Cobertura XML, lcov, Go's cover profile or the JSON of coverage.py. broom runs no tests. Without a report they name the command that writes one.
- `broom diagnose` lists the tests that repeat one another, with both places and the lines they share.
- Two new hints: `skipped_test`, for a change that adds a test marked skipped with no condition behind it, and `untested_file`, for a change that adds a code file of 30 lines or more with no test file named for it.

---

### Smells

- A new hint, `deprecated_api`, for a change that adds a call to a deprecated API, in Python, Go, Rust and TS/JS. The hint carries the tool's own words, which usually name what replaced it. TS/JS needs tsgolint.

---

### Diagnosis

- `broom diagnose` lists the packages each project declares and nothing imports, with knip, deptry, cargo-machete and `go mod tidy -diff`. A tool that isn't installed is named once and never asked for.
- `broom diagnose --vulnerabilities` asks osv-scanner for the known vulnerabilities of your dependencies. It sends package names and versions to osv.dev, so it runs only with the flag.

---

### Setup

- `broom doctor` lists the optional tools for the repo's languages after the gaps. None of them is a gap, and none is offered at session start.

---

### Check-up

- Three more counters: calls to deprecated APIs, duplicate test blocks, and the lines no test reaches by your coverage report. Claude is told once when one grew.

---

## 0.21.2 — 2026-11-17

---

### Check-up

- At session start broom counts five signs of rot across the repo: lint suppressions, skipped tests, TODO comments older than 180 days, dead code and public code with no doc comment. The first count is taken silently. After that Claude is told once when a number grew, with the files that added to it. `broom diagnose` lists them all.

---

### Smells

- Two new hints: `missing_docs`, for a change that adds public code with no doc comment, in Python, Go and Swift, and `broad_catch`, for a change that adds a handler that catches every error, in Python.
- Two checks that ran at once, as when two agents commit Go code together, made the second golangci-lint fail on its lock file, so its smells went unmeasured. It may now run beside another one.

---

## 0.21.1 — 2026-11-17

---

### Smells

- Rust gets 7 more smells from the clippy run broom already makes: long functions, complexity, nesting, dead code, `todo!()` and `unimplemented!()`, a `Result` dropped with `let _ =`, and unused parameters. It had 7 and has 14. A Rust function that is too long is also told when a change touches it.

---

## 0.21.0 — 2026-11-17

---

### Tests

- Running broom's test suite no longer writes into the data directory your sessions read. Before, a test run left known issues, caches and ledger lines there. After, the run gets a directory of its own, and a test that reaches for the real one fails.

---

## 0.20.1 — 2026-11-17

---

### Diagnosis

- `broom diagnose` measures a whole repo with no time cut and no file limit, and gives a report to read and, with `--json`, data: the smells by kind and by language, the hotspots, the worst smells, the tools that were missing and the counts of `broom stats`.
- Hotspots are ranked by their smells and by how often they changed in the last 90 days, so a bad file that changes every week comes before a bad file nobody touches. `broom smells --by smells` keeps the order by smells alone.
- `broom compare BASE` says what the work since a revision did to the smells: what is gone, new, smaller and bigger, and one line to quote.

---

## 0.20.0 — 2026-11-17

---

### Smells

- A change is told the old smells in the code it touches. Before, an edit inside a function that was already too long said nothing as long as the function didn't grow past a limit. After, it gets a hint that says `you touched it, clean it up in this change`, for a function, a type or a file, and in Python for parameters, nesting and complexity too. Code the change doesn't touch stays quiet.
- A function, a type or a file that was already past the hard limit can't grow on a reason alone. Before, `broom known --accept` let each added line through. After, the block marks the finding as one that can't be accepted, and accepting leaves it out and says what size to bring it back to.

---

## 0.19.2 — 2026-11-17

---

### Diagnosis

- `broom stats` counts what a session would otherwise write a script to count: lines of code by language and folder, the longest files, the tests with the skipped ones and the code files that have none, the lint suppressions and the TODO comments with their age, and the files that changed most and changed together. It needs git and no other tool.
- The session card names it, so Claude asks broom before it writes a script.

---

## 0.19.1 — 2026-11-17

---

### Sweep

- A block says how to fix what it found. It opens with what was blocked and what to do, lists the findings, then gives the usual fix of each kind of smell among them and says what is not a fix. The way to accept a finding moved from the first line to the last.
- `broom fixes` prints the usual fix of each smell, and `/broom:clean` asks it instead of carrying a table of its own.

---

### Smells

- At the start of a session in a repo with code, Claude is told the bar before it writes: the repo's limits, what blocks for being added, how a finding passes and which broom command answers a question about the repo.

---

## 0.19.0 — 2026-11-17

---

### Sweep

- A finding passes fixed, or accepted with a reason. Before, running the same commit again let a lint finding through, and stopping a turn twice recorded what was left as known, both without a reason. After, a blocked finding blocks again until it is fixed or `broom known --accept "<why>"` is run, at a commit and at a turn's end alike. Stopping again still ends the turn and leaves what is left open.
- `broom known --accept` also accepts what the last blocked turn end showed, and then says `stop again`.

---

### Record

- A change that loosens the bar is recorded and shown in the turn's line, never blocked: a `.broom.json` that turns a smell off, raises a limit or excludes a path, a new lint suppression, and a `git commit --no-verify`. `broom report` counts them by kind.
- A finding that a looser `.broom.json` hides doesn't count as fixed.

---

### Setup

- `broom doctor` lists git's pre-commit hook as a gap in a repo with code that has none, with `broom install-hook` as its fix, so `/broom:setup` offers it with the missing tools. `broom doctor` exits 1 for such a repo until the hook is added or the gap is dismissed.

---

## 0.18.2 — 2026-11-17

---

### Record

- broom keeps a record of what it did with each finding. Every block, fix, pass and skip leaves a line, with the hook it came from, and a repo and its linked worktrees share one record. Before, a finding that was fixed left no trace, so nobody could say whether the checks work.
- `broom report` prints that record for a repo over a period: findings blocked, fixed and let through with the fix rate, the same per rule, the tools that were skipped and the seconds each check took.
- A turn that let something through says so in one line at its end, such as `broom let 3 through this turn: 2 magic_numbers (retry), 1 function_lines (accepted: <why>)`. It is not shown with `check_on` at `commit`.

---

### Docs

- The docs are reorganized: one question per doc, with a roadmap, goals with dates and a record of each decision.

---

## 0.18.1 — 2026-11-16

---

### Fixes

- A Stop hook that ran until Claude Code ended it at its timeout is made hard to repeat. It happened in 18 of 130 Stops of one session, over about 90 minutes. No Stop took between a few seconds and the timeout.
- The cause on that machine isn't confirmed, since it didn't reproduce here. What was found is fixed:
  - Tool output was read through pipes. A tool that exits and leaves a daemon behind keeps those pipes open, as a language server or git's file system monitor does.
  - `run()` then waited for the daemon: 12.0 s for a tool that took no time, beside a daemon that slept 12 s. After a timeout it waited with no limit.
  - Output now goes to files that are read when the command is done. A command reads no input.
  - `git cat-file` ran on every check outside the hook's 25 seconds, with 60 of its own. It goes through the same limits now.
  - git is told not to start its file system monitor for any command broom starts. It also takes no optional index lock and asks for no password.
  - The hook's input was read until its pipe closed, in the commit hook's launcher too. It is read until it parses.
  - A state file's lock is waited for 5 seconds at most.
- A hook still running after 20 seconds writes `hook-trace.log` in broom's data directory. It shows where each thread is and what processes it started, so a repeat says whether broom or a tool held the hook.
- The per-path caches of golangci-lint and clippy are kept 7 days instead of 30. Every worktree an agent makes has a path of its own, and one data directory held 844 MB of them.

---

## 0.18.0 — 2026-11-16

---

### Sweep

- One run of any hook takes at most 30 seconds. Every hook in `hooks.json` has that `timeout` now. Before, the commit and stop hooks had 300 and the async ones had none.
- The commands of one run share 25 seconds. A command that runs out is killed with everything it started, so a linter's compiler no longer keeps running after it.
- At 28 seconds the hook gives up and lets the commit, edit or stop through. A check cut off never blocks, and its content isn't recorded as passed.
- A session-start scan that ran out of time keeps its count as a floor, such as "at least N", and runs again.
- Where `broom install-hook` added git's own hook, that hook does the commit check on the files the commit really takes. The PreToolUse hook can only guess them from the command, so it only formats.

---

### Speed

- Checks that passed aren't run again. Content that passed is recorded file by file, so one file with a hint no longer makes the other 19 run again at each try.
- A clean batch took 74 commands the first time and 1 after. With one hint it took 73, 71 and 71 before.
- What the smell measurers found in a file is kept for a day by its content. A second check of 30 Go files took 3.8 s and 18.5 CPU-seconds, where it took 8.5 s and 48.6.
- A session scan after a new commit took 0.8 s on a 3,184-file repo, where it took 4.0.
- broom's clippy run keeps its own config path and target directory. It and the project's own clippy run no longer make cargo check the crate again each time.
- git is asked once per repo what is tracked and what differs. One 30-file check started 15 git processes where it started 262. Another started 8 where it started 505.
- A check that ran out of time is skipped for 20 minutes in every session and agent, with a note.
- Each tool a hook starts is kept to a quarter of the cores through `GOMAXPROCS`, `RAYON_NUM_THREADS` and `CARGO_BUILD_JOBS`, unless you set them.
- Next to a busy foreground job the check took 11.8 s instead of 9.7. The job kept 97 to 104 percent of its speed instead of 73 to 82.
- A lower priority was measured and left out. `nice 10` changed nothing, and macOS's background class made the check 3.6 times slower.
- `tsc --incremental` was measured and left out. On 800 modules it took 0.75 s where a full check took 0.81, and TypeScript 7 takes 0.08.
- jscpd's whole-repo scan was measured and left as it was. It took 2.9 s on a 9,279-file repo, once per distinct change.

---

### Fixes

- Hooks that run at once no longer lose one another's changes to the state they share. Six processes making 40 changes each kept 58 of the 240 before, and all 240 now.
- Each read, change and write of that state holds a lock: the passed record, known issues, the last blocked commit, notes, setup answers and the measurement cache.
- ruff, golangci-lint and clippy are read from their JSON instead of their text. golangci-lint's text "for loop can be changed to use an integer range (Go 1.22+)" had its closing parenthesis read as the linter's name. That made it a compile error that blocks a commit.

---

### Smells

- A new hint, `folder_cycle`: an import the change adds that leads into a folder whose files lead back to this one. The layers then go the wrong way.
- broom reads Python's imports itself. TS/JS's are read by dependency-cruiser, which `broom doctor` offers.
- dependency-cruiser needs a TypeScript below 7 beside it. Without one it reads no `.ts` file and says nothing, so broom names each changed file it didn't read.

---

## 0.17.0 — 2026-11-15

---

### Smells

- Smells that need the project's own checkout run there, where imports and dependencies resolve. Before, they ran in the scratch copy of the changed files.
- Go's typed linters run there: `debug_output`, `globals`, `commented_code` and `dead_code` from `unused`.
- TS/JS and Python import cycles run there, as a new smell: `import_cycle`.
- clippy runs there for Rust: `params`, `bool_params`, `debug_output`, `type_escape` and `suppression`.
- With no copy of the base to compare with, such a finding counts when it is on a line the change added.
- The scan at session start gives these tools 60 seconds between them, quick ones first. It says what it skipped.
- TS/JS get `bool_params`, `type_lines`, `globals` and `commented_code` from four oxlint rules of broom's own. They live in `defaults/oxlint-rules.mjs` as an oxlint JS plugin, so they need Node.
- TS/JS get `unused_params` and `broad_test_asserts` from oxlint and its Jest rules.
- Python gets `nested_ternary`, and Go gets `type_escape`.
- Swift gets `debug_output`, `nested_ternary`, `globals` and unlabeled `bool_params` as SwiftLint custom rules.
- Python and TS/JS now have a source for every smell.
- `commented_code` is a hint in TS/JS and Go, whose detectors guess. It blocks in Python.
- Rust and CSS files count for `file_lines` and `duplicate_lines`.

---

### Fixes

- Swift 6.4 colors its diagnostics even into a pipe. That hid every compile error from broom, so a commit that broke a call in another file went through. They are read now.
- Swift 6.4 words a missing XCTest as `unable to resolve module dependency`, so the fallback that builds the sources without the tests never ran. It runs now.

---

### Setup

- `broom doctor` asks for Node in a TS/JS repo, and for jscpd in a Rust or CSS one.

---

### Cleanup

- `broom smells` ends its list with how many smells `--top` cut off.
- The clean skill gets a table of the usual fix for each smell. It also gets a rule for a repo whose tests already fail.

---

### Internals

- broom was measured by its own bar again: 23 smells, now none.
- `checks.py` became four modules of 44 to 234 lines, where it had 529. `measure.py` became three, where it had 412 lines.
- `broom init` got its own module, and the longest functions were split.
- 131 tests pass, also on a machine where five Swift tests failed before.

---

## 0.16.4 — 2026-11-15

---

### Settings

- A linked worktree without a `.broom.json` reads the main worktree's.
- One repo's `.broom.json` was ignored by a global gitignore. The worktrees its agents worked in never had it, so they ran with broom's defaults instead of the repo's limits and excludes.
- `broom doctor` says where the file was read from, and when git ignores it.

---

### Fixes

- Files outside any git repo are neither formatted per edit nor recorded for the turn's end, such as a subagent's draft script in a temp folder.
- Style findings in one such draft once stopped a session's turn. 0.16.3's pass records happened to drop these files already, and now it is deliberate.
- jscpd gets a baseline only from a base git can resolve. A missing git ref had read as "version 5 or later needed", so a failure note now quotes jscpd.

---

### Internals

- broom was measured by its own bar: 35 smells with 4 past the hard limit, now 23 with none past it.
- `diagnose` became a method per language, where it had 184 lines and a complexity of 45. `plan` became a grouping class, where it had a complexity of 25.
- The 1001-line test file became five files of 161 to 257 lines. `common.py` became four modules of 92 to 274 lines, where it had 577.
- The commit gate left `hooks.py` for its own module, which took `hooks.py` from 409 lines to 231.
- Files over 400 lines went from 5 to 1.
- Nothing else changed in behavior: 111 tests pass, and every subcommand's `--help` is unchanged.

---

## 0.16.3 — 2026-11-15

---

### Sweep

- `broom install-hook` adds git's own pre-commit hook. It checks the commits Claude Code's commit hook never sees, such as a wrapper script's or a person's.
- That hook checks the staged files the same way, without formatting. It never replaces another tool's hook, and it passes over a broom too old to know it.
- `BROOM_NO_ACCEPT=1` turns `broom known --accept` off for agents that must fix what they break. The block message then stops offering it.

---

### Speed

- File content that passed a check is recorded by git's blob id for a day, and no hook checks it again. It counts as passed when nothing blocked, hinted or timed out.
- On a TypeScript repo where checking a 29-file commit took 55 to 81 s, the skip takes about 30 ms.

---

### Settings

- `legacy` in `.broom.json` names code on its way out. New code that repeats it isn't a duplicate, as during a migration that writes the new code beside the old.
- `test_limits` in `.broom.json` moves the smell limits for test files, on top of `limits`. A repo with file limits of 150 and 200 lines for its source had split a test file into four numbered parts to fit.

---

### Cleanup

- `broom smells` names the missing tools in its first line. Without them its counts read as cleaner than the code is.

---

## 0.16.2 — 2026-11-15

---

### Speed

- Session start no longer waits for a smell scan. The scan runs in an async hook, and its note reaches Claude with the next turn. The session hook says only what a cached scan knows.
- On a 2,376-file repo the session hook takes 0.13 to 0.24 s. The scan inside it took 13 to 36 s. Once in six runs it passed its 30 s timeout and lost the result and the cache.

---

### Sweep

- The turn-end check waits while background work runs, such as a test suite, a build or a subagent. It waits half an hour at most and checks at the turn that work wakes.
- A hint no longer stops Claude in a pause and has it change files under a running test suite.
- The turn-end check sees what Bash changed, such as sed, a codemod or `git mv`. It also sees what a wrapper script committed.
- Both are measured against HEAD as the prompt found it. An async prompt hook notes the working tree, which took 0.2 s on the same repo and holds up no prompt.
- A subagent's edits are checked at its own end, and the block goes to it, so it fixes its own work. The main session's turn end no longer checks them for it.

---

## 0.16.1 — 2026-11-14

---

### Smells

- `build`, `out`, `release` and `target` count as build output only where git doesn't track their files.
- A repo that keeps hand-written code in a `release/` folder had its smells there unreported. Five files only that folder imported were called dead.
- Untracked build folders stay skipped, since the list was made for an unignored `node_modules` and app build.
- A note lists the tracked folders still skipped by name, such as `vendor` and `generated`.
- Generated code counts as using code, so what only it calls isn't dead.
- A renamed file is measured against its old path, and none of its lines count as changed. That holds for `git mv` and for a move staged with `git add`.
- A moved file over the hard limit no longer blocks as new. Its old lint findings and dead code stay quiet.
- A long file whose lines other than imports didn't grow isn't longer for the change. Rewiring imports after a move no longer blocks a commit when a formatter wraps them.

---

### Cleanup

- `broom smells --base REV` lists only what the changes since REV made worse. The JSON gives each smell's size or count at REV as `was`.
- `broom smells` and the session note leave out `.broom.json`'s `exclude`, as formatting and checks already did.

---

### Speed

- On a 2,376-file TypeScript repo the new steps add about 0.25 s to a whole-repo scan of 15 to 20 s. They add about 0.2 s to a hook's check.
- The scan finds the same 915 smells as 0.16.0.

---

## 0.16.0 — 2026-11-13

---

### Cleanup

- `broom smells [paths] [--top N] [--json]` ranks the code smells of the repo or some paths. It lists the hotspot files and the worst smells, furthest past their limit first.
- `/broom:clean` cleans up worst first, in small batches the user agrees to. It keeps behavior, and each batch is checked again and committed.
- At session start broom asks Claude to raise the repo's smells past the hard limit at a natural point. Claude offers `/broom:clean` and doesn't clean up unasked.
- That scan runs once per commit. `broom smells --dismiss` quiets it until the count grows.
- A whole-repo scan no longer calls its smells new.
- `broom doctor` shows `limits` and `smells_off` from `.broom.json`.

---

## 0.15.0 — 2026-11-13

---

### Smells

- Dead code is found with jscpd's `--dead-code`: a file, export, symbol or import that nothing uses. In TS/JS and Python a change that adds one gets a hint.
- Tests and entry points are left out. `smells_off: ["dead_code"]` turns it off where code loads dynamically.

---

## 0.14.0 — 2026-11-13

---

### Smells

- Duplicate code is found with jscpd 5. A new duplicate block with a side in the change's files hints past 10 lines and blocks past 30.
- It is found anywhere in the repo and compared with the base revision, so old copies stay quiet.
- Clones between two test files don't count, nor clones of generated or vendored code.

---

### Setup

- `broom doctor` checks for jscpd wherever smells measure code, so `/broom:setup` offers it: `npm i -g jscpd`.

---

## 0.13.0 — 2026-11-13

---

### Smells

- Smells that count each time they appear. A change is blocked when it adds a lint suppression without a reason, a swallowed error or empty block, or commented-out code.
- A change gets a hint when it adds unused parameters, magic numbers, debug prints, TODOs, type escapes, globals, boolean flag parameters or too broad test assertions.
- Long types hint too, past 250 lines.
- Such a smell counts when the change raises its count in a file. A moved or edited line that keeps it doesn't count.
- Magic numbers in tests don't count.
- Go measures only what linters that read syntax alone can see. Repeated literals, globals and debug prints need types, and the scratch copy's imports don't resolve.
- `Generated/` and `testdata/` are skipped like other generated and fixture code.

---

### Settings

- `smells_off` in `.broom.json` turns single smells off.

---

## 0.12.1 — 2026-11-13

---

### Smells

- Smells skip dependencies, environments and build output, such as `node_modules`, `.venv`, `dist`, `release` and `target`. They also skip minified files, `.d.ts` files and generated code.
- A repo with an unignored `node_modules` and app build put 58,000 files in a sweep's scope. The smell pass over them now takes under 3 seconds.
- Less noise, measured on four of the author's repos. Complexity in tests doesn't count, since each assertion's `if` adds to it. Neither do `describe` and `it` callbacks, which are containers.

---

### Speed

- The base version of the files is read with one `git cat-file --batch` instead of a `git show` per file. A path with a space no longer breaks the read.

---

## 0.12.0 — 2026-11-13

---

### Smells

- Code smells: long functions and files, many parameters, deep nesting, high complexity and nested ternaries. They are measured against broom's own limits in every repo.
- The soft limits are 50 for function lines, 400 for file lines, 5 for parameters, 4 for nesting and 10 for complexity. The hard limits are 100, 1000, 8, 6 and 20.
- They are measured with ruff and Python's `ast`, oxlint, golangci-lint and SwiftLint.
- Only what a change made worse counts: pushed past a limit, or grown while past the hard one.
- Past the soft limit a smell is a hint, in the commit's context and once at a turn's end.
- Past the hard limit it blocks the commit. Like a type error it passes only fixed or accepted with `broom known --accept "<why>"`.
- `broom sweep` lists the smells the changes made worse, and `--all` every smell in the repo.
- The `smells` setting turns them off, and `limits` in `.broom.json` moves them per repo.

---

### Sweep

- Stopping a turn twice no longer records type errors or severe smells as known, so the commit still stops on them.

---

## 0.11.0 — 2026-11-13

---

### Settings

- Settings start at defaults and are never asked. Change one in `/config` or `.broom.json` when you disagree with its default.
- `/broom:setup` asks at most two questions, both before acting on your machine or repo: install the missing tools, and add formatter configs.
- `check_on` defaults to `stop`, so broom checks the files Claude edited at every turn's end as well as at a commit.
- The commit hook sees only Claude's own commits. With the old default, a user who commits by hand got no checks.

---

### Internals

- Tests run against an empty Claude config, so the user's own settings no longer leak in.

---

## 0.10.0 — 2026-11-13

---

### Sweep

- Type and compile errors don't pass on a retry alone. A blocked commit that holds them passes once they're fixed, or after `broom known --accept "<why>"`.
- `broom known --accept` records the blocked result as known with the reason.
- Lint findings still pass the second time unchanged.
- Before, a subagent could commit 167 tsc errors by running the same commit twice, without a word.
- `broom known` lists the reason next to each accepted issue.

---

## 0.9.0 — 2026-09-27

---

### Languages

- Swift is linted with SwiftLint. The project's `.swiftlint.yml` is used where it has one, run from the outermost so nested configs apply and `excluded` holds.
- Without one, broom's defaults find bugs only: SwiftLint's "lint" and "performance" rules plus `force_cast` and `force_try`.
- The defaults hold no naming or length rule. They skip CocoaPods, Carthage and `.build`.
- SwiftPM packages are compile-checked with `swift build --build-tests`. Errors count anywhere, so a changed signature blocks on its callers.
- Warnings don't count, since SwiftPM prints them only for the files it recompiles.
- The Command Line Tools without Xcode have neither XCTest nor swift-testing. There the tests are left out with a note, instead of blocking on `no such module 'XCTest'`.
- Xcode projects aren't built.
- Swift is formatted where the project configures swift-format with `.swift-format` or SwiftFormat with `.swiftformat`.
- `broom init` adds a `.swift-format` with Xcode's 4-space indent and 120 columns. swift-format comes with Swift 6 and later, so there's nothing to install.

---

### Language servers

- A language server for `.swift`: sourcekit-lsp, which pushes diagnostics. It was checked in Claude Code 2.1.283.
- In an Xcode project without a `Package.swift` it reads one file at a time, so calls into other files show as errors.
- `format_scope=function` counts computed properties as functions, SwiftUI's `body` among them.

---

### Setup

- `broom doctor` finds Swift by the files git tracks, in packages and Xcode apps alike.
- It checks that the toolchain runs. On macOS `swift` and `sourcekit-lsp` are shims until Xcode or the Command Line Tools are installed.
- It flags the official `swift-lsp` plugin, which serves the same files.

---

## 0.8.0 — 2026-09-26

---

### Setup

- Setup is done once for every repo. Its answers are remembered by kind of gap instead of per repo, so a gap you left alone in one repo isn't raised in the next.
- `broom setup --reset` forgets them.
- `/broom:setup` recommends installing JS/TS tools machine-wide, with devDependencies as the other way. `broom doctor --json` gives the first as `fix_global`.
- `/broom:setup` skips the when-to-run and scope questions once they're user settings.
- `broom doctor --json` gives each setting's value and its source: `repo`, `user` or `default`. It marks the gaps already answered.

---

## 0.7.0 — 2026-09-23

---

### Language servers

- `broom lsp typescript` starts typescript-language-server wherever it's installed.
- It uses the project's TypeScript up to 6. A TypeScript 7 project and a repo without TypeScript get its bundled TypeScript 6.
- Before, broom ran TypeScript 7's `tsc --lsp`, which sends diagnostics only on request. Claude Code never makes that request, so Claude saw no type errors from broom's server.
- `tsc --lsp` is now the fallback when typescript-language-server is missing.
- This covers what the official `typescript-lsp` plugin does, so that plugin can go. `broom doctor` still flags it, since only one server per extension runs.

---

### Setup

- `broom doctor` reports the TypeScript server the launcher will start, and asks for typescript-language-server where it's missing.
- It no longer calls a TypeScript older than 7 broken.

---

## 0.6.1 — 2026-09-23

---

### Fixes

- Commits written as `T=~/repo; git -C $T commit` or `git -c key=val commit` are checked. Claude Code's `if` patterns never matched them, so they committed unchecked.
- The commit hook now sees every Bash call. A shell prefilter in `hooks/commit.sh` lets through only input that mentions `git` and `commit`, in about 13 ms.
- The command parser follows the variables a command sets.
- Go: golangci-lint gets a results cache per module path. The shared cache replayed file paths from another folder, such as a worktree of the same repo or a deleted copy. broom then dropped every issue as not in the commit.

---

### Internals

- A test that needs `oxfmt` is skipped where it isn't installed.

---

## 0.6.0 — 2026-09-23

---

### Languages

- Less joins CSS and SCSS. It is linted with the project's stylelint, else with broom's defaults.
- The defaults extend `stylelint-config-recommended-less`, which you install in the project, and accept CSS modules.
- They change two things in that config. stylelint's core hex check covers declarations too, and the duplicate-variable rule is off, since redefining a variable is legal Less.
- One false positive is known: a detached ruleset call, `@r();`.

---

### Language servers

- The CSS language server serves `.less` too, with the same Tailwind and `composes` settings.

---

### Setup

- `broom doctor` finds Less files and offers the Less config as a devDependency.

---

## 0.5.1 — 2026-09-23

---

### Fixes

- broom's stylelint defaults skip build output and `*.min.css`, as its oxlint defaults do. Build output is `dist`, `build`, `out` and `coverage`.
- A committed built or vendored CSS file no longer blocks a commit.

---

## 0.5.0 — 2026-09-23

---

### Languages

- CSS and SCSS are linted with the project's stylelint, biome or ESLint with `@eslint/css`. The last two lint plain CSS only.
- Without any of them, stylelint runs with broom's defaults, which report errors and not style.
- The defaults use stylelint-config-recommended's rules for CSS and `stylelint-config-recommended-scss` for SCSS. Both accept Tailwind v3 and v4 and CSS modules.
- Without that SCSS config in the project, SCSS is skipped with a note.

---

### Language servers

- A language server for `.css` and `.scss`: vscode-css-language-server, set up to accept Tailwind's at-rules and `composes`.

---

### Formatting

- `format_scope=function` widens CSS to the innermost rule around each changed line.

---

### Setup

- `broom doctor` finds CSS and SCSS at any depth and reports their linter, formatter and language server.
- `broom init` turns on oxfmt for CSS outside JS projects.
- Formatting itself is unchanged. The project's biome, oxfmt or prettier already formatted CSS and SCSS.

---

## 0.4.0 — 2026-09-23

---

### Formatting

- `format_scope=function` widens the changed lines to the functions around them. It asks the language servers in broom's `.lsp.json` for them with `documentSymbol`.
- When no server answers it falls back to the changed lines, with a note.

---

### Settings

- A `.broom.json` per repo: `format_on`, `check_on` and `format_scope` override the user settings in that repo.
- Its `exclude` globs keep generated or vendored paths out of everything.
- `broom doctor` validates the file.

---

### Install

- broom runs on Python 3.9 and later, and is tested on macOS's system Python.
- It has an MIT `LICENSE`.

---

## 0.3.0 — 2026-09-23

---

### Setup

- `broom doctor` lists the repo's languages, missing or broken tools, missing configs and dependencies not installed. Each comes with the command that fixes it.
- A broken tool is such as a rustup proxy without its component, or a TypeScript older than 7 for the language server.
- It names the plugins whose language servers compete with broom's.
- One config at the root covers a monorepo.
- A SessionStart hook runs the doctor, cached in about 0.1 s. When the repo has gaps it asks Claude to offer `/broom:setup`.
- That happens once per session. After `broom setup --done` or `--dismiss` it doesn't happen again until the gaps change.
- `/broom:setup` replaces `/broom:init`. It asks what to install, whether to turn formatting on, when broom runs and the format scope.
- JS/TS tools are installed as devDependencies, with `-w` or `-W` at pnpm and yarn workspace roots.

---

### Formatting

- The `format_scope` option: `changed`, the default, keeps only the formatter's edits on changed lines, for every formatter. `file` formats whole files.

---

### Sweep

- `/broom:sweep` takes plain language.
- `broom sweep` gained `--staged`, `--base REV`, `--all`, `--scope` and `--include-known`. `--all` reports only, unless `--fix` is given.
- `broom sweep` sums up big results.
- `broom known` lists and clears accepted issues, and sweeps say how many are hidden.
- Missing tools never block a commit, and the report suggests `/broom:setup`.

---

### Languages

- Solution-style tsconfigs, with `"files": []` and references, are type-checked per referenced config.

---

### Settings

- `broom` run from Bash reads the plugin options from the settings file, since only hooks get them as variables.

---

## 0.2.0 — 2026-09-23

---

### Install

- Renamed from `lint@claude-code-lint` to `broom@claude-code-broom`.

---

### Sweep

- broom runs on `git commit` by default. It formats the files the commit takes and stages them again, lints and type-checks them, and denies the commit while issues remain.
- Files only partly staged are left unformatted, and `--no-verify` skips the check.
- `bin/broom` is on the Bash PATH with `sweep`, `fmt` and `init`. Skills call it instead of script paths.

---

### Settings

- The `userConfig` options `format_on` and `check_on` show in `/config`. `format_on` takes commit, edit or off, and `check_on` takes commit, stop or off.
- The hooks after each edit and at each turn's end exit in about 15 ms unless enabled.

---

### Fixes

- Hooks use the exec form, so the "re-read the file" message after formatting is gone.

---

### Internals

- An end-to-end test suite in `tests/`.

---

## 0.1.0 — 2026-09-23

---

### Sweep

- Format on every edit, a lint gate at every stop, and language servers for Go, TS/JS, Rust and Python.
