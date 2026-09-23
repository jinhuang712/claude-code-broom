# Design

## Parts

| Part | Role |
|---|---|
| `hooks/hooks.json` | SessionStart (offer setup), PreToolUse on `git commit` (the sweep), PostToolUse on edits and Stop (both opt-in) |
| `bin/broom` | The one entry point, for hooks and for people; on the Bash PATH while the plugin is enabled |
| `.lsp.json` | Language servers Claude Code starts: gopls, `tsc --lsp`, rust-analyzer, pyright, vscode-css-language-server |
| `skills/` | `/broom:setup` and `/broom:sweep`, which call `broom` |
| `lib/broom/` | `gitcmd` reads commits, `fmt` formats, `checks` runs linters, `gate` decides what counts, `doctor` diagnoses, `lsp` asks servers for function ranges |
| `defaults/` | Lint configs used only where a project has none, and the tool registry for installs |

Python 3.9+ standard library only. State lives in `~/.claude/plugins/data/broom-claude-code-broom/`.

## A commit

1. The PreToolUse hook fires only for Bash calls matching `git commit *` or `git -C *`; Claude Code evaluates that
   condition itself. broom parses the command: `cd`, `git -C`, `-a`, `--no-verify`, `git add` in the same
   command, and flags inside a heredoc message that must not count.
2. It works out the files the commit takes. The hook runs before the command, so for `git add . && git commit`
   it predicts what that add will stage.
3. It formats them and re-stages what was staged in full. A partly staged file is left alone, so its unstaged
   hunks can't slip in.
4. It lints and type-checks, then filters (next section). Issues deny the commit with a report.
5. Committing the same result again passes and records the issues as known.

## What counts

Lint findings count on lines that differ from the base (`git diff -U0`; an untracked file counts whole). Compile
and type errors count anywhere, including files nobody touched. A known issue is keyed on file, tool, rule,
message and the line's text, so it stays known when lines above it move. Known issues expire after 30 days.

## Format scopes

- `file`: the formatter's output as is.
- `changed`: format the whole file, diff it against the original, and undo every hunk that doesn't touch a
  changed line. Line-for-line hunks are decided per line; re-wrapped hunks go in or out whole. This works with
  every formatter, including those with no range support.
- `function`: first widen the changed lines to the outermost function or method around them, from the language
  server's `documentSymbol`. No answer means `changed`, with a note. CSS has no functions, so there it is the
  innermost rule (or Sass mixin or `@function`) around each line: a nested rule, not the rule it sits in.

## Setup

`broom doctor` scans for marker files (`go.mod`, `package.json`, `Cargo.toml`, `pyproject.toml`, …) three levels
deep, lists the tools each language needs, and runs each one to prove it works, which catches a rustup proxy
without its component. CSS has no marker file, so it goes by the `.css` and `.scss` files git tracks, at any depth,
each counted with its nearest `package.json` (else the repo root). Untracked files are left out: listing them walks
the working tree, about 160 ms on a 6,000-file repo against 25 ms for tracked files. It flags missing configs, collapsed to one fix at the repo root since configs are found by
walking up, and plugins whose language servers claim the same files as broom's.

The SessionStart hook runs a cached doctor. The cache key includes the modification time of every PATH
directory, so installing a tool invalidates it. When there are gaps it asks Claude, once per session, to offer
`/broom:setup`. `broom setup --done` or `--dismiss` stores a hash of the gaps, and broom stays quiet until they
change.

## Settings

A setting resolves in this order: the repo's `.broom.json`, then the plugin's user settings, then the default.
Hooks receive user settings as environment variables; `broom` run from Bash reads them from the settings file.
`.broom.json` holds only choices and path globs, never commands, so honoring it in an untrusted repo is safe.

## Claude's context and Serena

After a formatter rewrites a file, Claude Code shows Claude the diff of any file it had read, and the Edit tool
accepts a changed file as long as `old_string` still matches. Serena re-reads a file whose modification time
changed. Claude Code's language servers, though, only hear about edits made through Edit and Write, so a file a
formatter rewrote can show stale diagnostics until Claude edits it again.

## The CSS language server's settings

vscode-css-language-server validates a file only once it has settings for that file's language. When `.lsp.json`
gives a server `settings`, Claude Code (checked in 2.1.280, not documented) offers `workspace/configuration` and
answers each section from them, so broom's entry has a `css` and an `scss` section; a missing one silences that
language. Without `settings` the server uses its defaults, which flag every Tailwind directive as an unknown
at-rule. broom's sections turn that check off and accept CSS modules' `composes`.

## Limits

- Only commits Claude makes are checked. Commits you make in a terminal are not.
- `function` scope costs a language server start per language, about 0.05 to 1 second.
- A cold `cargo clippy` can time out; that check is then skipped for the rest of the session.
- The scan looks three levels deep and at up to 20 projects per language.
- CSS means `.css` and `.scss`: no Less, no indented Sass, no `<style>` blocks in `.vue` or `.svelte` files.
- vscode-langservers-extracted, which ships the CSS server, last released in May 2024 (4.10.0).
