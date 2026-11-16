# 023. typescript-language-server is the TypeScript server, and `tsc --lsp` the fallback

Decided: 2026-09-23

---

## The problem

Claude Code only takes diagnostics a server pushes. TypeScript 7's `tsc --lsp` sends them only on request, so Claude saw no type errors from broom's server.

---

## The choice

A launcher starts typescript-language-server wherever it is installed and falls back to `tsc --lsp`.

---

## Not chosen

- **`tsc --lsp` alone**: It gives navigation and no diagnostics under Claude Code.

---

## Consequences

The user installs one more tool. The official `typescript-lsp` plugin serves the same files, and only one server per extension runs.
