# Proposal

## The problem

Claude writes code quickly, and nothing holds that code to the project's formatter, linter and type checker until
CI or a human reviewer does. The pieces to fix that exist, but they don't add up:

- Claude Code runs language servers only when a plugin declares them. The official TypeScript plugin wraps
  `typescript-language-server`, which needs `tsserver`, and TypeScript 7 no longer ships it.
- A hook that lints after every edit is slow and noisy: mid-change warnings push Claude into early fixes.
- Many repos have no formatter config, or the tools aren't installed, so any hook quietly does nothing.
- Checking whole files buries a small change under a legacy repo's old warnings.

## The proposal

One plugin that does three things:

1. **Set up.** Detect what a repo needs, and install and configure it with the user's consent.
2. **Sweep.** At the right moments, format, lint and type-check Claude's changes, and hold them back until they're
   clean.
3. **See.** Declare language servers so Claude gets diagnostics as it edits.

## Alternatives considered (September 2026)

| Option | Why not on its own |
|---|---|
| Official LSP plugins (`gopls-lsp`, `typescript-lsp`, …) | Language servers only; `typescript-lsp` breaks with TypeScript 7 |
| everything-claude-code | A very large bundle (900+ skills); gofmt only, no golangci-lint or oxlint |
| SonarQube plugin | Needs a SonarQube account and Docker; per-edit analysis is a SonarQube Cloud feature |
| Semgrep Guardian | Security scanning only; needs a login |
| claudekit | Built around ESLint and tsc; installs by editing `settings.json` |
| A hand-written PostToolUse hook, as in Oxc's docs | Runs on every edit, TS only, unaware of the project's other tools |
| pre-commit or lefthook | Excellent for people; not aware of Claude: no changed-line scoping, no memory of accepted issues, no setup |

broom borrows from several of them: the "format on edit, gate at stop" layering from bengous/claude-code-plugins,
curated golangci-lint choices from samber/cc-skills-golang, and Oxc's recommended hook.
