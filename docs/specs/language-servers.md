# Language servers

This part declares the language servers Claude Code starts, so Claude sees diagnostics as it edits. Two of them need more than a name: TypeScript's and CSS's.

---

## How Claude Code starts a server

Claude Code expands `${CLAUDE_PLUGIN_ROOT}` in an LSP command and starts it from the session's directory. The plugin's `bin/` is on the Bash tool's PATH but not on the server's, so a bare `broom` would not be found. Both were checked in 2.1.280.

Claude Code only takes diagnostics a server pushes with `publishDiagnostics`. It never requests them with `textDocument/diagnostic`.

---

## The TypeScript launcher

`.lsp.json` starts `${CLAUDE_PLUGIN_ROOT}/bin/broom lsp typescript`, which picks a server and replaces itself with it, so the server owns stdin and stdout.

```
typescript-language-server installed?
├── Yes   start it: the project's tsserver (TypeScript 6 and older), else its bundled TypeScript 6
└── No    start tsc --lsp: the project's TypeScript 7, then the global one
```

TypeScript 7's `tsc --lsp` sends diagnostics only on request, so under Claude Code it gives navigation and no diagnostics. typescript-language-server pushes them. Since 6.0 it falls back to its bundled TypeScript 6, also in TypeScript 7 projects, which ship no `tsserver`.

The choice follows the session's directory: one server per session, so a monorepo gets the TypeScript at its root.

- [023: typescript-language-server is the TypeScript server](decisions/023-typescript-server.md)

---

## The CSS server's settings

vscode-css-language-server validates a file only once it has settings for that file's language. When `.lsp.json` gives a server `settings`, Claude Code offers `workspace/configuration` and answers each section from them. That was checked in 2.1.280 and is not documented.

broom's entry has `css`, `scss` and `less` sections, and a missing one silences that language. Without `settings` the server uses its defaults, which flag every Tailwind directive as an unknown at-rule. broom's sections turn that check off and accept CSS modules' `composes`.

vscode-langservers-extracted, which ships the CSS server, last released in May 2024 at 4.10.0.

---

## Swift in an Xcode project

sourcekit-lsp reads an Xcode project without a `Package.swift` one file at a time. A call into another file shows as "Cannot find … in scope", and errors within the file are real. A build server that bridges Xcode's build settings, such as xcode-build-server, fixes that. broom doesn't set one up.
