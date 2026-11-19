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
Which server can start?
├── broom's own typescript-language-server   it has a TypeScript 6 beside it
├── the PATH's typescript-language-server    the project's TypeScript or the one beside the server is below 7
└── neither                                  tsc --lsp: the project's TypeScript 7, then the global one
```

TypeScript 7's `tsc --lsp` sends diagnostics only on request, so under Claude Code it gives navigation and no diagnostics. typescript-language-server pushes them. It ships no TypeScript of its own: it loads the project's `tsserver`, else the `typescript` package Node finds beside the server. TypeScript 7 ships no `tsserver`, so in a project on TypeScript 7 a server beside a TypeScript 7 exits at start. Which TypeScript sits beside a server is read from the `package.json` files Node would search, with no process started.

broom's own copy lives under its data directory. The command that installs its dependency-cruiser installs this server too.

The choice follows the session's directory: one server per session, so a monorepo gets the TypeScript at its root.

- [023: typescript-language-server is the TypeScript server](decisions/023-typescript-server.md)
- [037: broom's own copy holds the TypeScript server too](decisions/037-own-typescript-server.md)

---

## The CSS server's settings

vscode-css-language-server validates a file only once it has settings for that file's language. When `.lsp.json` gives a server `settings`, Claude Code offers `workspace/configuration` and answers each section from them. That was checked in 2.1.280 and is not documented.

broom's entry has `css`, `scss` and `less` sections, and a missing one silences that language. Without `settings` the server uses its defaults, which flag every Tailwind directive as an unknown at-rule. broom's sections turn that check off and accept CSS modules' `composes`.

vscode-langservers-extracted, which ships the CSS server, last released in May 2024 at 4.10.0.

---

## Swift in an Xcode project

sourcekit-lsp reads an Xcode project without a `Package.swift` one file at a time. A call into another file shows as "Cannot find … in scope", and errors within the file are real. A build server that bridges Xcode's build settings, such as xcode-build-server, fixes that. broom doesn't set one up.
