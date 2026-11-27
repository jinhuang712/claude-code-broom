# Architecture

broom is a Claude Code plugin. Claude Code starts one of its hooks at a session start, a prompt, a Bash call, a Bash command that failed, an edit and a turn's end. The hook runs the project's tools on what changed, then exits with a block, a note or nothing.

```
Claude Code
  │ SessionStart · UserPromptSubmit · PreToolUse(Bash) · PostToolUse(edit) · PostToolUseFailure(Bash) · Stop · SubagentStop
  ▼
hooks/hooks.json ──▶ hooks/*.sh ──────▶ bin/broom ──▶ lib/broom/
                                            ▲              │
git pre-commit hook ────────────────────────┘              ├──▶ the project's tools (formatters, linters, type checkers)
skills/ (setup · status · scan · clean) ───▶ bin/broom    ├──▶ defaults/ (configs where a project has none)
.lsp.json ──▶ language servers                             ├──▶ <repo>/.broom/ (what broom found in that repo)
                                                           └──▶ the data directory (state shared by every repo)
```

---

## Hook declarations

They say which Claude Code events start broom, with a 30-second timeout each. The Bash hooks and the synchronous prompt hook go through a shell prefilter first, which leaves before Python starts when there is nothing to do.

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
- [Edit check](edit-check.md)
- [What counts](what-counts.md)
- [Smells](smells.md)
- [Format scopes](format-scopes.md)
- [Setup](setup.md)
- [Settings](settings.md)
- [Cleanup](cleanup.md)
- [Record](record.md)
- [Stats](stats.md)
- [Diagnosis](diagnosis.md)
- [Check-up](checkup.md)

---

## Default configs

They are lint configs used only where a project has none, broom's own oxlint rules, the ast-grep rules that read smells from a syntax tree and the registry of tools with their install commands.

They live in `defaults/`.

---

## Skills

They tell Claude how to run a setup, a status report, a scan and a cleanup with the `broom` command. The first three are commands the user types, and Claude alone loads the fourth.

They live in `skills/`.

---

## Language servers

`.lsp.json` at the root names the servers Claude Code starts: gopls, a launcher that picks the TypeScript server, rust-analyzer, pyright, sourcekit-lsp and vscode-css-language-server.

- [Language servers](language-servers.md)

---

## Where state lives

What broom finds in a repo lives in `.broom/` at the root of the repo's main checkout, which git ignores and every linked worktree shares: known issues, the repo's ledger, the last blocked result, the check-up's counters, the session scan, passed content and a check that ran out of time. A file there names a file of the repo by its path from the root, so a moved repo keeps it.

The rest lives in `~/.claude/plugins/data/broom-claude-code-broom/`: the tools' caches, sessions and claims, setup answers, the doctor's cache, the hook trace and an index of the repos that have a `.broom/`. A repo whose `.broom/` git tracks, or whose root broom can't write, keeps its records in a folder there.

- [053: What broom finds in a repo lives in the repo's `.broom/`](decisions/053-findings-live-in-the-repo.md)

- [Hook limits](hook-limits.md)
- [Record](record.md)

---

## Tests

They run the hooks and commands end to end against temporary repos.

They live in `tests/`.
