# Features

## Hooks

| Hook | Fires on | Does | Cost when idle |
|---|---|---|---|
| SessionStart | new, resumed and cleared sessions | Runs a cached doctor; if the repo has gaps, asks Claude to offer `/broom:setup` (once per session) | ~0.1 s |
| PreToolUse | every Bash call; acts on `git commit` | Formats the commit's files, lints and type-checks them, blocks the commit while issues remain | ~13 ms (a shell start); ~60 ms when the command mentions git and commit without committing |
| PostToolUse | Edit, Write, MultiEdit, Serena's edit tools | Formats per edit (`format_on=edit`); records files for the stop check (`check_on=stop`) | one Python start: 30–45 ms measured on macOS |
| Stop | each turn end | Checks the files Claude edited this turn (`check_on=stop`) | one Python start: 30–45 ms measured on macOS |

## Skills

- **`/broom:setup`**: runs the doctor, asks up to four questions (install tools, turn formatting on, when broom
  runs, format scope), acts on the answers, verifies, and records the decision.
- **`/broom:sweep`**: sweeps a scope you describe in your own words ("what I staged", "the last 3 commits",
  "this branch", "src/api", "the whole repo") and reports what's left.

## Commands

`broom` is on the Bash PATH while the plugin is enabled.

| Command | |
|---|---|
| `broom sweep` | Format, lint and type-check uncommitted changes. `--staged`, `--base REV`, `--all` (report only unless `--fix`), `--check`, `--scope`, `--include-known`, paths |
| `broom fmt [paths]` | Format only. `--scope` |
| `broom doctor [--json]` | Languages, tools, configs and conflicts, with the commands that fix them |
| `broom init [dir]` | Add default configs where missing. Never overwrites. `--dry-run` |
| `broom known [--clear] [paths]` | List or clear accepted issues |
| `broom setup --done / --dismiss / --reset` | Record the setup decision; gaps left alone are remembered by kind for every repo. `--reset` forgets them all |

## Settings (`/config`)

| Setting | Values | Default |
|---|---|---|
| `format_on` | `commit`, `edit` (also after every edit), `off` | `commit` |
| `check_on` | `commit`, `stop` (also at every turn end), `off` | `commit` |
| `format_scope` | `changed`, `function`, `file` | `changed` |

## Per-repo `.broom.json`

```json
{
  "format_scope": "function",
  "check_on": "stop",
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
