# broom

A Claude Code plugin for autonomous code hygiene. broom sets up the formatters, linters, type checkers and
language servers a repo needs, sweeps Claude's work with them (by default whenever Claude commits), and gives
Claude the language servers that show it its mistakes as it types.

It never reformats code it has no rules for, never raises old issues in lines nobody touched, and never
installs anything you didn't agree to.

## What it does

| | |
|---|---|
| 🧰 **Set up** | At session start broom checks the repo: languages, missing or broken tools, missing configs, and plugins that fight over the same files. When something's off, Claude offers **`/broom:setup`**, asks you what to install and how broom should behave, and does it. |
| 🧹 **Sweep** | When Claude runs `git commit`, broom formats the files going in, lints the lines that changed, type-checks the project, and blocks the commit until it's clean. You can also ask for a sweep anytime with **`/broom:sweep`**, in your own words. |
| 👁️ **See** | Language servers for Go (gopls), TS/JS (TypeScript 7's `tsc --lsp`), Rust (rust-analyzer) and Python (pyright) feed Claude diagnostics after every edit. Language servers only run in Claude Code through a plugin, so this is the part only a plugin can do. |

## Settings (`/config`)

| Setting | Default | Other values |
|---|---|---|
| `format_on` | `commit`: format what a commit takes | `edit`: also after every edit · `off` |
| `check_on` | `commit`: lint and type-check a commit, block it while issues remain | `stop`: also when Claude ends a turn · `off` |
| `format_scope` | `changed`: only the formatter's edits on changed lines, like an IDE's "only VCS changed text" | `file`: whole files |

`/broom:setup` asks about these, so you rarely set them by hand.

## A commit, step by step

1. **Which files:** the staged ones; for `-a` also tracked changes; for `git add … && git commit` in one command,
   what that add will stage; for `git commit <paths>`, those paths.
2. **Format** them with the project's own formatter, in the configured scope, and re-stage. A file staged only in
   part is left alone, so unstaged hunks never slip into the commit.
3. **Lint and type-check.** Lint findings count only on changed lines; compile and type errors count anywhere,
   since a changed signature breaks callers in files nobody touched.
4. **Decide.** Issues deny the commit with a report; Claude fixes them and commits again. Committing the same
   result again lets it through and records the issues as known, so a false positive costs one round, never a
   loop. `broom known` lists them. Missing tools never block a commit; broom suggests `/broom:setup` instead.
   `--no-verify` skips broom, as it skips git's own hooks.

## Tools

| | Format | Lint | Type / compile check | Language server |
|---|---|---|---|---|
| Go | `gofmt`; at commit the project's golangci formatters (gofumpt, goimports) | `golangci-lint` | golangci typecheck + `go vet ./...` | `gopls` |
| TS/JS | the project's `biome` / `oxfmt` / `prettier` | the project's `oxlint` / `eslint` / `biome`, else `oxlint` with broom's defaults (type-aware) | `tsc --noEmit`, per referenced config for solution-style tsconfigs | `tsc --lsp` (TypeScript 7) |
| Rust | `rustfmt` | `cargo clippy` | clippy errors | `rust-analyzer` |
| Python | `ruff format` | `ruff check` | — | `pyright` |

broom uses each project's own configs and tools first (from `node_modules/.bin`, then `PATH`). JS/TS and Python
are formatted only where a formatter is configured; `/broom:setup` adds one if you want it. In a monorepo, one
config at the root covers every package.

## Commands

`broom` is on the Bash PATH while the plugin is enabled.

| Command | |
|---|---|
| `broom sweep` | format, lint and type-check: `--staged`, `--base HEAD~3`, `--all` (report only unless `--fix`), `--check`, `--scope`, paths |
| `broom fmt [paths]` | format only |
| `broom doctor [--json]` | languages, tools, configs and conflicts, with the commands that fix them |
| `broom init [dir]` | add default configs where missing; never overwrites |
| `broom known [--clear]` | issues accepted as known |
| `broom setup --done / --dismiss` | record the setup decision for this repo |

## With Serena and Claude's context

- The commit check reads what is being committed, whichever tool wrote it: Edit, Serena, Bash or a person.
- After a formatter rewrites a file, Claude Code shows Claude the diff of any file it had read, and the Edit tool
  accepts a changed file as long as `old_string` still matches. Serena re-reads a file whose modification time
  changed. Formatting at commit rather than per edit keeps Claude's next edit from missing text a formatter
  just rewrote.
- Claude Code's language servers hear about files changed through Edit and Write. A file rewritten by a
  formatter or a script can show stale diagnostics until Claude edits it again.

## Install

```bash
claude plugin marketplace add ~/dev/claude-code/claude-code-broom
claude plugin install broom@claude-code-broom
```

Then start a session in a repo and accept Claude's offer to run `/broom:setup`, or run it yourself. It installs
the tools it's missing: JS/TS tools as devDependencies, Go/Rust/Python tools with brew, go install, rustup or uv.

The plugin loads in place from this folder: edits take effect on `/reload-plugins`, no version bump needed.
Don't also enable `gopls-lsp`, `typescript-lsp`, `rust-analyzer-lsp` or `pyright-lsp`: when two servers claim one
file extension, only the first registered starts. `broom doctor` flags that.

## Development

```bash
python3 -m unittest discover -s tests -v
claude plugin validate .
```

State lives in `~/.claude/plugins/data/broom-claude-code-broom/`.
