# Changelog

## 0.17.0

- Smells that need the project's own checkout, where imports and dependencies resolve, run there and not in the
  scratch copy of the changed files: Go's typed linters (`debug_output`, `globals`, `commented_code`, and
  `dead_code` from `unused`), TS/JS and Python import cycles (a new smell, `import_cycle`), and clippy for Rust
  (`params`, `bool_params`, `debug_output`, `type_escape`, `suppression`). With no copy of the base to compare
  with, a finding counts when it is on a line the change added. The scan at session start gives these tools 60
  seconds between them, quick ones first, and says what it skipped.
- TS/JS get `bool_params`, `type_lines`, `globals` and `commented_code` from four oxlint rules of broom's own
  (`defaults/oxlint-rules.mjs`, an oxlint JS plugin, so they need Node), `unused_params` and `broad_test_asserts`
  from oxlint and its Jest rules. Python gets `nested_ternary`; Go `type_escape`; Swift `debug_output`,
  `nested_ternary`, `globals` and unlabeled `bool_params`, as SwiftLint custom rules. Python and TS/JS now have a
  source for every smell. `commented_code` is a hint in TS/JS and Go, whose detectors guess, and blocks in Python.
- Rust and CSS files count for `file_lines` and `duplicate_lines`.
- Swift 6.4 colors its diagnostics even into a pipe, which hid every compile error from broom, so a commit that
  broke a call in another file went through; and it words a missing XCTest as `unable to resolve module
  dependency`, so the fallback that builds the sources without the tests never ran. Both are read now.
- `broom doctor` asks for Node in a TS/JS repo, and for jscpd in a Rust or CSS one.
- `broom smells` ends its list with how many smells `--top` cut off. The clean skill gets a table of the usual
  fix for each smell, and a rule for a repo whose tests already fail.
- broom measured by its own bar again: 23 smells, now none. `checks.py` (529 lines) became four modules of 44 to
  234 lines, `measure.py` (412) three, `broom init` its own module, and the longest functions were split. 131
  tests, none failing on a machine where five Swift tests failed before.

## 0.16.4

- A linked worktree without a `.broom.json` reads the main worktree's. One repo's `.broom.json` was ignored by a
  global gitignore, so the worktrees its agents worked in never had it and ran with broom's defaults instead of
  the repo's limits and excludes. `broom doctor` says where the file was read from, and when git ignores it.
- Files outside any git repo, such as a subagent's draft script in a temp directory, are neither recorded for the
  turn's end nor formatted per edit. Style findings in one such draft once stopped a session's turn; 0.16.3's pass
  records already happened to drop these files, and now it is deliberate.
- jscpd gets a baseline only from a base git can resolve, and a failure note quotes jscpd: a missing git ref had
  read as "version 5 or later needed".
- broom measured by its own bar: 35 smells, 4 of them past the hard limit, now 23 and none past it. `diagnose`
  (184 lines, complexity 45) becomes a method per language; `plan` (complexity 25) a grouping class; the
  1001-line test file five files of 161 to 257 lines; `common.py` (577 lines) four modules of 92 to 274 lines;
  the commit gate leaves `hooks.py` (409 to 231 lines) for its own module. Files over 400 lines: 5 to 1. No
  behavior changes beyond the three above: 111 tests, every subcommand's `--help` unchanged.

## 0.16.3

- `broom install-hook` adds git's own pre-commit hook, for commits Claude Code's commit hook never sees: a
  wrapper's (`kgf save`, an integration script) or a person's. It checks the staged files the same way, without
  formatting; it never replaces another tool's hook, and passes over a broom too old to know it.
- File content that passed a check, with nothing blocked, hinted or timed out, is recorded by git's blob id for a
  day, and no hook checks it again. On a TypeScript repo where checking a 29-file commit took 55 to 81 s, the skip
  takes about 30 ms.
- `.broom.json` `legacy` names code on its way out: new code that repeats it isn't a duplicate, as during a
  migration that writes the new code beside the old before deleting it.
- `.broom.json` `test_limits` moves the smell limits for test files on top of `limits`. A repo with 150- and
  200-line file limits for its source had split a test file into four numbered parts to fit.
- `BROOM_NO_ACCEPT=1` turns `broom known --accept` off, and the block message stops offering it, for agents that
  must fix what they break.
- `broom smells` names missing tools in its first line, where counts without them read as cleaner than the code
  is.

## 0.16.2

- Session start no longer waits for a smell scan. The scan runs in an async hook and its note reaches Claude with
  the next turn; the session hook says only what a cached scan knows. On a 2,376-file repo the session hook takes
  0.13 to 0.24 s, where the scan inside it took 13 to 36 s and passed its 30 s timeout once in six runs, losing the
  result and the cache.
- The turn-end check waits while background work runs (a test suite, a build, a subagent), for half an hour at
  most, and checks at the turn that work wakes. A hint no longer stops Claude in a pause and has it change files
  under a running test suite.
- The turn-end check sees what Bash changed (sed, a codemod, `git mv`) and what a wrapper committed (`kgf save`, an
  integration script), measured against HEAD as the prompt found it. An async prompt hook notes the working tree;
  it took 0.2 s on the same repo, which no prompt waits for.
- A subagent's edits are checked at its own end (SubagentStop) and the block goes to it, so it fixes its own work;
  the main session's turn end no longer checks them for it.

## 0.16.1

- `build`, `out`, `release` and `target` count as build output only where git doesn't track the files. A repo
  that keeps hand-written code in a `release/` directory had its smells there unreported, and five files only that
  directory imported were called dead. Untracked ones stay skipped: the list was made for an unignored
  `node_modules` and app build. A note lists the tracked directories still skipped by name (`vendor`,
  `generated`, ...), and generated code counts as using code, so what only it calls isn't dead.
- A renamed file (`git mv`, or a move staged with `git add`) is measured against its old path, and none of its
  lines count as changed: a moved file over the hard limit no longer blocks as "new", and its old lint findings
  and dead code stay quiet.
- A long file whose lines besides imports didn't grow isn't longer for the change: rewiring imports after a move,
  wrapped by a formatter, no longer blocks a commit.
- `broom smells --base REV` lists only what the changes since REV made worse, with each smell's size or count at
  REV as `was` in the JSON.
- `broom smells` and the session note leave out `.broom.json`'s `exclude`, as formatting and checks already did.
- On a 2,376-file TypeScript repo the new steps add about 0.25 s to a whole-repo scan of 15 to 20 s, and about
  0.2 s to a hook's check; the scan finds the same 915 smells as 0.16.0.

## 0.16.0

- `broom smells [paths] [--top N] [--json]`: the code smells of the repo or some paths, ranked: the hotspot files
  and the worst smells, furthest past their limit first.
- `/broom:clean`: a cleanup worst first, in small batches the user agrees to, behavior kept and each batch
  re-checked and committed.
- At session start, when the repo has smells past the hard limit, broom asks Claude to raise them and offer
  `/broom:clean` at a natural point, not to clean up unasked. The scan runs once per commit. `broom smells
  --dismiss` quiets it until the count grows.
- A whole-repo scan no longer calls its smells "new". `broom doctor` shows `.broom.json`'s `limits` and
  `smells_off`.

## 0.15.0

- Dead code, with jscpd's `--dead-code`: a file, export, symbol or import that nothing uses, in TS/JS and Python,
  gets a hint when the change added it. Tests and entry points are left out. `smells_off: ["dead_code"]` turns
  it off where code loads dynamically.

## 0.14.0

- Duplicate code, with jscpd 5: a new duplicate block with a side in the change's files hints past 10 lines and
  blocks past 30. It's found anywhere in the repo, and compared with the base revision so old copies stay quiet.
  Clones between two test files, and of generated or vendored code, don't count.
- `broom doctor` checks for jscpd (`npm i -g jscpd`) wherever smells measure code, so `/broom:setup` offers it.

## 0.13.0

- Smells that count by occurrence. A change that adds a lint suppression without a reason, a swallowed error or
  empty block, or commented-out code is blocked; one that adds unused parameters, magic numbers, debug prints,
  TODOs, type escapes, globals, boolean flag parameters or too broad test assertions gets a hint. Long types (over
  250 lines) hint too.
- An occurrence counts when the change raises the count in a file; a moved or edited line that keeps its
  occurrence doesn't. Magic numbers in tests don't count.
- `.broom.json` `smells_off` turns single smells off.
- Go measures only what linters reading syntax alone can see: repeated literals, globals and debug prints need
  types, and the scratch copy's imports don't resolve.
- `Generated/` and `testdata/` are skipped like other generated and fixture code.

## 0.12.1

- Smells skip dependencies, environments and build output (`node_modules`, `.venv`, `dist`, `release`, `target`,
  ...), minified files, `.d.ts` and generated code. A repo with an unignored `node_modules` and app build put
  58,000 files in a sweep's scope; the smell pass over them now takes under 3 seconds.
- The base version of the files is read with one `git cat-file --batch` instead of a `git show` per file, and a
  path with a space no longer breaks the read.
- Less noise, measured on four of the author's repos: complexity in tests doesn't count (each assertion's `if`
  adds to it), and neither do `describe`/`it` callbacks, which are containers.

## 0.12.0

- Code smells: long functions and files, many parameters, deep nesting, high complexity and nested ternaries,
  measured against broom's own limits in every repo (soft 50/400/5/4/10 for function lines, file lines,
  parameters, nesting and complexity; hard 100/1000/8/6/20) with ruff and Python's `ast`, oxlint, golangci-lint
  and SwiftLint. Only what a change made worse counts: pushed past a limit, or grown while past the hard one.
- Past the soft limit a smell is a hint, in the commit's context and once at a turn's end. Past the hard limit it
  blocks the commit, and like a type error passes only fixed or accepted with `broom known --accept "<why>"`.
- `broom sweep` lists the smells the changes made worse, `--all` every smell in the repo. Turn them off with the
  `smells` setting; `.broom.json` `limits` moves them per repo.
- Stopping a turn twice no longer records type errors or severe smells as known, so the commit still stops on
  them.

## 0.11.0

- Settings start at defaults and are never asked. `/broom:setup` asks at most two questions, both before acting
  on your machine or repo: install the missing tools, add formatter configs. Change a setting in `/config` or
  `.broom.json` when you disagree with its default.
- `check_on` defaults to `stop`: broom checks the files Claude edited at every turn end, as well as at commit. The
  commit hook only sees Claude's own commits, so with the old default a user who commits by hand got no checks.
- Tests run against an empty Claude config, so the user's own settings no longer leak in.

## 0.10.0

- Type and compile errors don't pass on a retry alone. A blocked commit that holds them passes once they're fixed,
  or after `broom known --accept "<why>"`, which records the blocked result as known with the reason. Lint findings
  still pass the second time unchanged. Before, a subagent could commit 167 tsc errors by running the same commit
  twice, without a word.
- `broom known` lists the reason next to each accepted issue.

## 0.9.0

- Swift. Linted with SwiftLint: the project's `.swiftlint.yml` where it has one (run from the outermost, so nested
  configs apply and `excluded` holds), else broom's defaults, which are bug-finders only: SwiftLint's "lint" and
  "performance" rules plus `force_cast` and `force_try`, no naming or length rules, CocoaPods, Carthage and `.build`
  skipped.
- SwiftPM packages are compile-checked with `swift build --build-tests`; errors count anywhere, so a changed
  signature blocks on its callers. Warnings don't count: SwiftPM prints them only for the files it recompiles. With
  the Command Line Tools and no Xcode, which have no XCTest or swift-testing, the tests are left out with a note
  instead of blocking on `no such module 'XCTest'`. Xcode projects aren't built.
- Swift is formatted where the project configures swift-format (`.swift-format`) or SwiftFormat (`.swiftformat`).
  `broom init` adds a `.swift-format` with Xcode's 4-space indent and 120 columns; swift-format comes with Swift 6
  and later, so there's nothing to install.
- A language server for `.swift`: sourcekit-lsp, which pushes diagnostics (checked in Claude Code 2.1.283). In an
  Xcode project without a `Package.swift` it reads one file at a time, so calls into other files show as errors.
  `format_scope=function` counts computed properties, SwiftUI's `body` among them, as functions.
- `broom doctor` finds Swift by the files git tracks, in packages and Xcode apps alike, checks that the toolchain
  runs (on macOS `swift` and `sourcekit-lsp` are shims until Xcode or the Command Line Tools are installed) and
  flags the official `swift-lsp` plugin, which serves the same files.

## 0.8.0

- Set up once for every repo. Setup answers are remembered by kind of gap, not per repo: a gap you left alone in
  one repo isn't raised in the next. `broom setup --reset` forgets them.
- `/broom:setup` recommends installing JS/TS tools machine-wide (`fix_global` in `broom doctor --json`), with
  devDependencies as the alternative, and skips the when-to-run and scope questions once they're user settings.
- `broom doctor --json` reports each setting's value and source (`repo`, `user`, `default`) and marks gaps
  already answered.

## 0.7.0

- TypeScript language server: `broom lsp typescript` starts typescript-language-server wherever it's installed.
  It uses the project's TypeScript (6 and older), or its bundled TypeScript 6 for TypeScript 7 projects and repos
  without one. Before, broom ran TypeScript 7's `tsc --lsp`, which sends diagnostics only on request; Claude Code
  never makes that request, so Claude saw no type errors from broom's server. It is now the fallback when
  typescript-language-server is missing.
- This covers what the official `typescript-lsp` plugin does, so it can go; `broom doctor` still flags it, since
  only one server per extension runs.
- `broom doctor` reports the TypeScript server the launcher will start and asks for typescript-language-server
  where it's missing. It no longer calls a TypeScript older than 7 broken.

## 0.6.1

- Commits written as `T=~/repo; git -C $T commit` or `git -c key=val commit` are checked. Claude Code's `if`
  patterns never matched them, so they committed unchecked. The commit hook now sees every Bash call: a shell
  prefilter (`hooks/commit.sh`, ~13 ms) lets through only input that mentions `git` and `commit`, and the command
  parser follows the variables a command sets.
- Go: golangci-lint gets a results cache per module path. The shared cache replayed another directory's file
  paths, from a worktree of the same repo or a deleted copy, and broom then dropped every issue as not in the commit.
- A test that needs `oxfmt` is skipped where it isn't installed.

## 0.6.0

- Less (`.less`) joins CSS and SCSS: linted with the project's stylelint, else with broom's defaults, which extend
  `stylelint-config-recommended-less` (install it in the project) and accept CSS modules. Two changes to that
  config: stylelint's core hex check also covers declarations, and the duplicate-variable rule is off, since
  redefining a variable is legal Less. One known false positive: a detached ruleset call (`@r();`).
- The CSS language server serves `.less` too, with the same Tailwind and `composes` settings.
- `broom doctor` finds Less files and offers the Less config as a devDependency.

## 0.5.1

- broom's stylelint defaults skip build output (`dist`, `build`, `out`, `coverage`) and `*.min.css`, as its oxlint
  defaults do. A committed built or vendored CSS file no longer blocks a commit once.

## 0.5.0

- CSS and SCSS are linted: with the project's stylelint, biome or ESLint with `@eslint/css` (the last two plain
  CSS only), else with stylelint and broom's defaults. The defaults report errors, not style:
  stylelint-config-recommended's rules for CSS, `stylelint-config-recommended-scss` for SCSS, both accepting
  Tailwind (v3 and v4) and CSS modules. Without that SCSS config in the project, SCSS is skipped with a note.
- A language server for `.css` and `.scss` (vscode-css-language-server), set up to accept Tailwind's at-rules and
  `composes`.
- `format_scope=function` widens CSS to the innermost rule around each changed line.
- `broom doctor` finds CSS and SCSS at any depth and reports their linter, formatter and language server;
  `broom init` turns on oxfmt for CSS outside JS projects. Formatting itself is unchanged: CSS and SCSS were
  already formatted by the project's biome, oxfmt or prettier.

## 0.4.0

- `format_scope=function`: widens the changed lines to the functions around them, asking the language servers in
  broom's `.lsp.json` (`documentSymbol`). Falls back to changed lines, with a note, when no server answers.
- Per-repo `.broom.json`: `format_on`, `check_on` and `format_scope` override the user settings in that repo;
  `exclude` globs keep generated or vendored paths out of everything. `broom doctor` validates the file.
- Runs on Python 3.9+ (tested on macOS's system Python). MIT `LICENSE`.

## 0.3.0

- `broom doctor`: languages, missing or broken tools (a rustup proxy without its component, TypeScript older than
  7 for the language server), missing configs, dependencies not installed, and plugins whose language servers
  compete with broom's, with the commands that fix each. One root config covers a monorepo.
- A SessionStart hook runs the doctor (cached, ~0.1 s) and, when the repo has gaps, asks Claude to offer
  `/broom:setup`. Once per session; not again after `broom setup --done` / `--dismiss` until the gaps change.
- `/broom:setup` replaces `/broom:init`: it asks what to install (JS/TS tools as devDependencies, with `-w`/`-W`
  at pnpm/yarn workspace roots), whether to turn formatting on, when broom runs, and the format scope.
- `format_scope` option: `changed` (default) keeps only the formatter's edits on changed lines, for every
  formatter; `file` formats whole files.
- `/broom:sweep` takes plain language; `broom sweep` gained `--staged`, `--base REV`, `--all` (report only unless
  `--fix`), `--scope` and `--include-known`, and summarizes big results.
- `broom known` lists and clears accepted issues; sweeps say how many are hidden.
- Missing tools never block a commit; the report suggests `/broom:setup`.
- Solution-style tsconfigs (`"files": []` plus references) are type-checked per referenced config.
- Bash-run `broom` reads the plugin options from the settings file, since only hooks get them as variables.

## 0.2.0

- Renamed from `lint@claude-code-lint` to `broom@claude-code-broom`.
- Runs on `git commit` by default: formats the files the commit takes, re-stages them, lints and type-checks,
  and denies the commit while issues remain. Partially staged files are left unformatted; `--no-verify` skips.
- `userConfig` options `format_on` (commit / edit / off) and `check_on` (commit / stop / off), shown in `/config`.
  The per-edit and end-of-turn hooks now exit in ~15 ms unless enabled.
- `bin/broom` on the Bash PATH (`sweep`, `fmt`, `init`); skills call it instead of script paths.
- Hooks use exec form; no more "re-read the file" message after formatting.
- End-to-end test suite in `tests/`.

## 0.1.0

- Format on every edit, lint gate at every stop, language servers for Go, TS/JS, Rust and Python.
