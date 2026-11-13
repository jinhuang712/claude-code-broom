# Features

## Hooks

| Hook | Fires on | Does | Cost when idle |
|---|---|---|---|
| SessionStart | new, resumed and cleared sessions | Runs a cached doctor; if the repo has gaps, asks Claude to offer `/broom:setup`. If it has smells past the hard limit, asks Claude to raise them and offer `/broom:clean` at a natural point. Once per session | ~0.1 s; a smell scan once per commit, under a second on the author's repos |
| PreToolUse | every Bash call; acts on `git commit` | Formats the commit's files, lints and type-checks them, blocks the commit while issues remain | ~13 ms (a shell start); ~60 ms when the command mentions git and commit without committing |
| PostToolUse | Edit, Write, MultiEdit, Serena's edit tools | Formats per edit (`format_on=edit`); records files for the stop check (`check_on=stop`) | one Python start: 30–45 ms measured on macOS |
| Stop | each turn end | Checks the files Claude edited this turn (`check_on=stop`) | one Python start: 30–45 ms measured on macOS |

## Skills

- **`/broom:setup`**: runs the doctor, asks at most two questions (install tools, turn formatting on), acts on
  the answers, verifies, and records the decision. Settings aren't asked: they start at defaults.
- **`/broom:sweep`**: sweeps a scope you describe in your own words ("what I staged", "the last 3 commits",
  "this branch", "src/api", "the whole repo") and reports what's left.
- **`/broom:clean`**: ranks the code smells of the repo or an area with `broom smells`, agrees a scope and batches
  with you, cleans up worst first keeping behavior and tests green, re-checks and commits each batch.

## Commands

`broom` is on the Bash PATH while the plugin is enabled.

| Command | |
|---|---|
| `broom sweep` | Format, lint and type-check uncommitted changes. `--staged`, `--base REV`, `--all` (report only unless `--fix`), `--check`, `--scope`, `--include-known`, paths |
| `broom fmt [paths]` | Format only. `--scope` |
| `broom doctor [--json]` | Languages, tools, configs and conflicts, with the commands that fix them |
| `broom init [dir]` | Add default configs where missing. Never overwrites. `--dry-run` |
| `broom smells [paths] [--top N] [--json] [--dismiss]` | The code smells of the repo or some paths: the hotspot files and the worst smells, worst first. `--dismiss` quiets the session note until the count past the hard limit grows |
| `broom known [--accept WHY] [--clear] [paths]` | List or clear accepted issues. `--accept WHY` accepts the last blocked commit's issues with the reason: how an unfixed type or compile error gets through |
| `broom setup --done / --dismiss / --reset` | Record the setup decision; gaps left alone are remembered by kind for every repo. `--reset` forgets them all |

## Settings (`/config`)

| Setting | Values | Default |
|---|---|---|
| `format_on` | `commit`, `edit` (also after every edit), `off` | `commit` |
| `check_on` | `stop` (at every turn end, and at commit), `commit` (only at commit), `off` | `stop` |
| `format_scope` | `changed`, `function`, `file` | `changed` |
| `smells` | `on`, `off` | `on` |

## Per-repo `.broom.json`

```json
{
  "format_scope": "function",
  "check_on": "commit",
  "exclude": ["vendor/**", "**/*.pb.go"]
}
```

At the git root. Any setting above overrides the user setting in this repo; `exclude` globs, relative to the
root, keep paths out of formatting and checks entirely. `broom doctor` flags unknown keys and values.

## Languages and tools

| | Format | Lint | Type / compile check | Language server |
|---|---|---|---|---|
| Go | gofmt; at commit the project's golangci formatters (gofumpt, goimports) | golangci-lint | golangci typecheck, `go vet ./...` | gopls |
| TS/JS | the project's biome, oxfmt or prettier | the project's oxlint, eslint or biome; else oxlint with broom's defaults (type-aware) | `tsc --noEmit`, per referenced config for solution-style tsconfigs | typescript-language-server, with the project's TypeScript (6 and older) or its bundled one |
| Rust | rustfmt | cargo clippy | clippy errors | rust-analyzer |
| Python | ruff format | ruff check | — | pyright |
| CSS, SCSS, Less | the project's biome, oxfmt or prettier | the project's stylelint, biome or ESLint with `@eslint/css` (the last two plain CSS only); else stylelint with broom's defaults | — | vscode-css-language-server |
| Swift | the project's swift-format or SwiftFormat | SwiftLint with the project's `.swiftlint.yml`; else with broom's defaults | `swift build --build-tests`, SwiftPM packages only | sourcekit-lsp |

Tools come from the project's `node_modules/.bin` first, then PATH. JS/TS, CSS, Python and Swift are formatted only
where a formatter is configured.

broom's Swift lint defaults are bug-finders, not style: the rules SwiftLint files under "lint" and "performance",
plus `force_cast` and `force_try`, with naming, length and layout rules off, and CocoaPods, Carthage and `.build`
code skipped. The compile check counts errors only: SwiftPM prints warnings just for the files it recompiles, so
they would come and go (sourcekit-lsp shows Claude the warnings as it edits). With macOS's Command Line Tools and no
Xcode there's no XCTest or swift-testing, so the check builds the sources and leaves the tests out, with a note.
Xcode projects without a `Package.swift` get formatting, linting and the language server, but no compile check, and
the language server reads them one file at a time, so calls into other files show as "Cannot find … in scope".
`broom init` turns Swift formatting on with swift-format, which the toolchain ships, and a `.swift-format` of
4-space indents (Xcode's) and 120 columns, where swift-format's own defaults are 2 and 100.

broom's CSS defaults report errors, not style: stylelint-config-recommended's rules for `.css`,
`stylelint-config-recommended-scss` for `.scss` and `stylelint-config-recommended-less` for `.less`. All three
accept Tailwind's directives and functions (v3 and v4) and CSS modules (`composes`, `:global`, `:export`), and skip
build output and `*.min.css`. The SCSS and Less configs have to be installed in the project; without them those
files aren't linted, with a note. The language server accepts the same Tailwind at-rules and `composes`. Sass's
indented syntax, Stylus, `<style>` blocks in `.vue` or `.svelte` files and CSS-in-JS aren't covered.

## Code smells

| Smell | Soft (hint) | Hard (block) | Python | TS/JS | Go | Swift |
|---|---|---|---|---|---|---|
| `function_lines` | 50 | 100 | `ast` | `max-lines-per-function` | `funlen` | `function_body_length` |
| `file_lines` | 400 | 1000 | broom counts lines, in every language | | | |
| `params` | 5 | 8 | `PLR0913` | `max-params` | `revive` `argument-limit` | `function_parameter_count` |
| `nesting` | 4 | 6 | `PLR1702` | `max-depth` | `nestif` | — |
| `complexity` | 10 | 20 | `C901` | `complexity` | `gocognit` | `cyclomatic_complexity` |
| `nested_ternary` | — | any | — | `no-nested-ternary` | — | — |
| `type_lines` | 250 | — | `ast` | — | — | `type_body_length` |
| `duplicate_lines` | 10 | 30 | jscpd | jscpd | jscpd | jscpd |

These count by occurrence: a change that adds one gets the smell's level.

| Smell | Level | Python | TS/JS | Go | Swift |
|---|---|---|---|---|---|
| `suppression` | block | `PGH003` `PGH004` | `ban-ts-comment` | `nolintlint` | `blanket_disable_command` |
| `swallowed_error` | block | `S110` | `no-empty` `no-useless-catch` | `revive` `empty-block` | `no_empty_block` |
| `commented_code` | block | `ERA001` | — | — | — |
| `unused_params` | hint | `ARG` | — | `revive` `unused-parameter` | `unused_parameter` |
| `magic_numbers` | hint | `PLR2004` | `no-magic-numbers` | `mnd` | `no_magic_numbers` |
| `debug_output` | hint | `T201` `T203` | `no-console` | — | — |
| `todo` | hint | `FIX` | `no-warning-comments` | `godox` | `todo` |
| `type_escape` | hint | `ANN401` | `no-explicit-any` `no-non-null-assertion` | — | `force_cast` `force_unwrapping` `force_try` |
| `globals` | hint | `PLW0603` | — | — | — |
| `bool_params` | hint | `FBT001` | — | `revive` `flag-parameter` | — |
| `broad_test_asserts` | hint | `PT011` | — | — | — |

- An occurrence counts when the change raises the count in a file. Lines match the base by text: a moved line
  stays old, and an edited line that keeps its occurrence adds nothing. A line counts once per smell.
- Unused variables and imports stay with the project's linter, which already reports them. In Go only linters
  that read syntax alone run, since the scratch copy's imports don't resolve: no repeated literals, globals or
  debug prints there.
- Duplicate code comes from jscpd 5, which scans every code file in the repo and, with `--baseline-from-ref`,
  the base tree: a clone counts when it is new and has a side in the change's files. Clones between two test
  files, and clones of generated or vendored code, don't count. `broom doctor` checks for jscpd.
- `dead_code` (a hint) comes from jscpd's `--dead-code`: a file, export, symbol or import nothing uses, in
  TS/JS and Python, tests and entry points left out. It counts on a line the change added, or in a new file.
  What loads dynamically (a manifest's scripts, plugins) looks unused too; turn it off per repo if so.
- `.broom.json` `smells_off` turns single smells off: `{"smells_off": ["magic_numbers", "debug_output"]}`.

- Each tool runs alone in a scratch copy with a config broom writes, so the project's lint config doesn't change
  the bar. Missing tools are skipped with a note.
- Only what a change made worse counts: each file is measured as it is and at the base revision (HEAD for hooks).
  A smell counts when the change pushed it past a limit, or grew it while past the hard one; growth between the
  limits is left alone.
- A hint goes into the commit's context, and stops a turn's end once. A block stops the commit and passes only
  fixed or accepted with `broom known --accept "<why>"`, like a type error.
- `broom sweep` lists the smells the changes made worse; `broom sweep --all` lists every smell in the repo.
- Dependencies, environments and build output (`node_modules`, `vendor`, `Pods`, `Carthage`, `.venv`, `venv`,
  `site-packages`, `__pycache__`, `.build`, `DerivedData`, `dist`, `build`, `out`, `release`, `target`, `.bundle`,
  `.next`, `coverage`, `test-results`, `testdata`, `Generated`, `generated`), minified files, `.d.ts` and generated code (`DO NOT EDIT`, `@generated`)
  are skipped.
- In tests, complexity and magic numbers don't count: every assertion's `if` adds to complexity, and the numbers
  are fixtures. Neither do the length or complexity of
  `describe`/`it`/`test` callbacks, which are containers. Long test functions still count.
- Swift has no control-flow nesting rule; complexity covers it.
- `.broom.json` `limits` moves a smell's bar per repo: `{"limits": {"function_lines": [60, 120]}}`.

## Doctor checks

- Each needed tool is on PATH and runs (a rustup proxy without its component fails here).
- The TypeScript language server gives Claude diagnostics: typescript-language-server is installed. Without it
  broom falls back to TypeScript 7's `tsc --lsp`, which gives navigation but no diagnostics.
- The project's configured tools resolve, or its dependencies need installing.
- Formatter configs exist; in a monorepo, one fix at the root.
- CSS, SCSS and Less files git tracks, at any depth and outside `node_modules`, build output and `*.min.css`, get
  their linter, formatter and language server checked like any language. So do Swift files, outside Pods, Carthage
  and `.build`, in SwiftPM packages and Xcode projects alike.
- The Swift toolchain runs: on macOS, `swift` and `sourcekit-lsp` are shims that fail until Xcode or the Command
  Line Tools are installed.
- No other plugin starts a language server for the same files.
- `.broom.json` is valid.

Fixes come out as ready commands: JS/TS and CSS tools as devDependencies with the project's package manager
(`-w`/`-W` at pnpm/yarn workspace roots), the rest through brew, go install, rustup, uv, npm, swiftly or
`xcode-select --install`.
`--json` also gives `fix_global`, with the JS/TS and CSS tools installed machine-wide, once for every repo.
