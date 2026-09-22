# broom

A Claude Code plugin that sweeps what Claude commits: it formats the files with each project's own formatter,
lints the lines that changed, type-checks, and blocks the commit until it's clean. It also brings the language
servers Claude Code's code intelligence needs for Go, TS/JS, Rust and Python.

## When it runs

| Setting (`/config`) | `commit` (default) | other values |
|---|---|---|
| `format_on` | format the files a `git commit` takes | `edit`: also after every edit · `off` |
| `check_on` | lint and type-check them; deny the commit while issues remain | `stop`: also when Claude ends a turn · `off` |

| Hook | Fires on | Cost when idle |
|---|---|---|
| PreToolUse, `if: Bash(git commit *)` / `Bash(git -C *)` | only commands with a git commit | none: Claude Code evaluates `if` without starting a process |
| PostToolUse on Edit, Write, MultiEdit and Serena's edit tools | every edit | ~15 ms, exits unless `format_on=edit` or `check_on=stop` |
| Stop | every turn end | ~15 ms, exits unless `check_on=stop` |

Language server diagnostics after each edit come from Claude Code itself, through `.lsp.json`.

## What a commit goes through

1. **Which files.** The staged files; for `-a` also tracked changes; for `git add … && git commit` in one
   command, the files that add will stage (the hook runs before the command); for `git commit <paths>`, those
   paths.
2. **Format** them and re-stage the ones that were staged in full. A file staged only in part is left
   unformatted, so its unstaged hunks never slip into the commit.
3. **Lint and type-check.** Lint findings count only on changed lines (git diff against HEAD; a new file counts
   whole), so a legacy repo's existing issues never land on Claude. Compile and type errors count anywhere: a
   changed signature breaks callers in files nobody touched.
4. **Decide.** Issues deny the commit with a report, and Claude fixes them and commits again. The same result
   committed again unchanged passes and is recorded as known (for 30 days), so a false positive or an old issue
   costs one round, never a loop. `--no-verify` skips broom, as it skips git's own hooks.

## Tools

| | Format | Lint | Type / compile check | Language server |
|---|---|---|---|---|
| Go | `gofmt`; at commit the project's golangci formatters (gofumpt, goimports) | `golangci-lint` | golangci typecheck + `go vet ./...` | `gopls` |
| TS/JS | the project's `biome` / `oxfmt` / `prettier`, if configured | the project's `oxlint` / `eslint` / `biome`, else `oxlint` with `defaults/oxlintrc.json` (type-aware) | `tsc --noEmit` | `tsc --lsp` (TypeScript 7) |
| Rust | `rustfmt` | `cargo clippy` | clippy errors | `rust-analyzer` |
| Python | `ruff format`, if ruff is configured | `ruff check` | — | `pyright` |

Project tools come from `node_modules/.bin` up to the git root, then `PATH`. JS/TS and Python files are
formatted only in projects that configure a formatter; `/broom:init` adds one.

## With Serena and Claude's context

- The commit check reads what is being committed, whichever tool wrote it: Edit, Serena, Bash or a person.
- After a formatter rewrites a file, Claude Code shows Claude the diff of any file it had read, and the Edit tool
  accepts a changed file as long as `old_string` still matches. Serena re-reads a file whose modification time
  changed and resyncs its language server. Formatting at commit, not per edit, also keeps Claude's next
  `old_string` from missing text a formatter just rewrote.

## Install

```bash
brew install golangci-lint ruff
npm i -g oxlint oxlint-tsgolint oxfmt typescript pyright
go install golang.org/x/tools/gopls@latest
rustup component add rust-analyzer clippy rustfmt

claude plugin marketplace add ~/dev/claude-code/claude-code-broom
claude plugin install broom@claude-code-broom
```

The plugin loads in place from this folder: edits take effect on `/reload-plugins`, no version bump needed.
Don't also enable `gopls-lsp`, `typescript-lsp`, `rust-analyzer-lsp` or `pyright-lsp` from the official
marketplace: when two servers claim one file extension, only the first registered starts.

## Commands

`broom` is on the Bash PATH while the plugin is enabled.

| | |
|---|---|
| `broom sweep [--check] [--staged] [paths]` | format, then lint and type-check the uncommitted changes (`/broom:sweep`) |
| `broom fmt [paths]` | format only |
| `broom init [--dry-run]` | add default configs where a project has none (`/broom:init`) |

## Development

```bash
python3 -m unittest discover -s tests -v
claude plugin validate .
```

State (known issues, per-session notes) lives in `~/.claude/plugins/data/broom-claude-code-broom/`.
