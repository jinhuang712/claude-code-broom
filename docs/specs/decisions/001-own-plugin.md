# 001. broom is one plugin of its own instead of a bundle of existing ones

Decided: 2026-09-23

---

## The problem

Claude's code met the project's formatter, linter and type checker only at CI or review. Pieces to fix that existed in September 2026, and none covered setup, checks and language servers together.

---

## The choice

One plugin sets a repo up, sweeps Claude's changes and declares language servers.

---

## Not chosen

- **Official LSP plugins**: They give language servers only.
- **everything-claude-code**: It is a bundle of 900+ skills with gofmt only, and no golangci-lint or oxlint.
- **SonarQube plugin**: It needs a SonarQube account and Docker, and per-edit analysis is a SonarQube Cloud feature.
- **Semgrep Guardian**: It scans for security only and needs a login.
- **claudekit**: It is built around ESLint and tsc, and installs by editing `settings.json`.
- **A hand-written PostToolUse hook, as in Oxc's docs**: It runs on every edit, covers TS only and knows nothing of the project's other tools.
- **pre-commit or lefthook**: They are not aware of Claude: no changed-line scoping, no memory of accepted findings and no setup.

---

## Consequences

broom borrows the "format on edit, gate at stop" layering from bengous/claude-code-plugins, curated golangci-lint choices from samber/cc-skills-golang and Oxc's recommended hook. broom's TypeScript server does inside broom what the official `typescript-lsp` plugin does.
