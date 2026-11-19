# 037. broom's own copy holds the TypeScript server too

Decided: 2026-11-19

---

## The problem

typescript-language-server ships no TypeScript. It loads the project's `tsserver`, else the `typescript` package Node finds beside the server. TypeScript 7 has no `tsserver`. With a global TypeScript 7 beside a global server, a project on TypeScript 7 leaves the server nothing to load, and it exits at start. Claude Code then says the language server couldn't start.

---

## The choice

The install command of broom's own copy adds typescript-language-server beside its TypeScript 6. The launcher starts that server first. It starts another one only where the project's TypeScript or the one beside that server is below 7, and falls back to `tsc --lsp` otherwise.

---

## Not chosen

- **Hand the server a `tsserver` path in `.lsp.json`**: The path differs per machine, and whether Claude Code expands a variable there was not checked.
- **Tell the user to install a global TypeScript 6**: It replaces their own TypeScript, as 036 already weighed.
- **`tsc --lsp` in TypeScript 7 projects**: It gives navigation and no diagnostics under Claude Code.

---

## Consequences

One install serves both the folder cycles and the diagnostics, and the user is asked once. Before the install a TypeScript 7 project gets `tsc --lsp`, which starts and gives no diagnostics.
