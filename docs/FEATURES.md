# Features

## Hooks

| Hook | Fires on | Does | Cost when idle |
|---|---|---|---|
| SessionStart | new, resumed and cleared sessions | Runs a cached doctor; if the repo has gaps, asks Claude to offer `/broom:setup` (once per session) | ~0.1 s |
| PreToolUse | Bash calls with `git commit` | Formats the commit's files, lints and type-checks them, blocks the commit while issues remain | none; Claude Code filters |
| PostToolUse | Edit, Write, MultiEdit, Serena's edit tools | Formats per edit (`format_on=edit`); records files for the stop check (`check_on=stop`) | ~15 ms |
| Stop | each turn end | Checks the files Claude edited this turn (`check_on=stop`) | ~15 ms |

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
| `broom setup --done / --dismiss` | Record the setup decision for this repo |

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
| TS/JS | the project's biome, oxfmt or prettier | the project's oxlint, eslint or biome; else oxlint with broom's defaults (type-aware) | `tsc --noEmit`, per referenced config for solution-style tsconfigs | `tsc --lsp` (TypeScript 7) |
| Rust | rustfmt | cargo clippy | clippy errors | rust-analyzer |
| Python | ruff format | ruff check | — | pyright |

Tools come from the project's `node_modules/.bin` first, then PATH. JS/TS and Python are formatted only where a
formatter is configured.

## Doctor checks

- Each needed tool is on PATH and runs (a rustup proxy without its component fails here).
- TypeScript is version 7 or later for the language server.
- The project's configured tools resolve, or its dependencies need installing.
- Formatter configs exist; in a monorepo, one fix at the root.
- No other plugin starts a language server for the same files.
- `.broom.json` is valid.

Fixes come out as ready commands: JS/TS tools as devDependencies with the project's package manager (`-w`/`-W` at
pnpm/yarn workspace roots), the rest through brew, go install, rustup or uv.
