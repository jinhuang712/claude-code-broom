# Architecture

broom is a Claude Code plugin. Claude Code starts one of its hooks at a session start, a prompt, a Bash call, an edit and a turn's end. The hook runs the project's tools on what changed, then exits with a block, a note or nothing.

```
Claude Code
  │ SessionStart · UserPromptSubmit · PreToolUse(Bash) · PostToolUse(edit) · Stop · SubagentStop
  ▼
hooks/hooks.json ──▶ hooks/commit.sh ──▶ bin/broom ──▶ lib/broom/
                                            ▲              │
git pre-commit hook ────────────────────────┘              ├──▶ the project's tools (formatters, linters, type checkers)
skills/ (setup · sweep · clean) ───▶ bin/broom             ├──▶ defaults/ (configs where a project has none)
.lsp.json ──▶ language servers                             └──▶ the data directory (state shared by every hook)
```

---

## Hook declarations

They say which Claude Code events start broom, with a 30-second timeout each. The Bash hook goes through a shell prefilter first.

They live in `hooks/`.

- [Hook limits](hook-limits.md)
- [Commit check](commit-check.md)

---

## The entry point

One command serves hooks and people. It is on the Bash tool's PATH while the plugin is enabled.

It lives in `bin/`.

---

## The library

It handles each hook, reads commits, formats, runs linters, decides what counts, measures smells, diagnoses a repo and asks language servers for function ranges. Settings, state, git access and the tool lookup are shared ground.

It lives in `lib/broom/`.

- [Commit check](commit-check.md)
- [Turn end](turn-end.md)
- [What counts](what-counts.md)
- [Smells](smells.md)
- [Format scopes](format-scopes.md)
- [Setup](setup.md)
- [Settings](settings.md)
- [Cleanup](cleanup.md)

---

## Default configs

They are lint configs used only where a project has none, broom's own oxlint rules and the registry of tools with their install commands.

They live in `defaults/`.

---

## Skills

They tell Claude how to run a setup, a sweep and a cleanup with the `broom` command.

They live in `skills/`.

---

## Language servers

`.lsp.json` at the root names the servers Claude Code starts: gopls, a launcher that picks the TypeScript server, rust-analyzer, pyright, sourcekit-lsp and vscode-css-language-server.

- [Language servers](language-servers.md)

---

## The data directory

State lives in `~/.claude/plugins/data/broom-claude-code-broom/`: known issues, passed content, the last blocked commit, per-session records and the tools' caches.

- [Hook limits](hook-limits.md)

---

## Tests

They run the hooks and commands end to end against temporary repos.

They live in `tests/`.
