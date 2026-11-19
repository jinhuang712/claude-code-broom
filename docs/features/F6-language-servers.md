# F6: Language servers

```
F6: Language servers
└── F6.1: Diagnostics as Claude edits — six servers
```

broom declares language servers, so Claude sees its mistakes as it edits.

---

## F6.1: Diagnostics as Claude edits

Six language servers give Claude diagnostics as it edits, one per language.

| Language | Server |
|---|---|
| Go | gopls |
| TS/JS | typescript-language-server, with the project's TypeScript at 6 and older, else a TypeScript 6 beside the server |
| Rust | rust-analyzer |
| Python | pyright |
| CSS · SCSS · Less | vscode-css-language-server |
| Swift | sourcekit-lsp |

In a project on TypeScript 7 the server needs a TypeScript 6 beside it. broom's own copy under its data directory has one, and `broom doctor` offers it as one command.

4 limits:

- Without a typescript-language-server that can start, broom falls back to TypeScript 7's `tsc --lsp`, which gives navigation and no diagnostics.
- The CSS server accepts Tailwind's at-rules and CSS modules' `composes`.
- In an Xcode project without a `Package.swift`, a call into another file shows as "Cannot find … in scope".
- When another plugin serves the same files only one server starts. `broom doctor` names every such plugin, also for a language the repo lacks, and `/broom:setup` offers to disable them.

- **How it works**: [Language servers](../specs/language-servers.md)
- **Why**:
  - [023: typescript-language-server is the TypeScript server](../specs/decisions/023-typescript-server.md)
  - [037: broom's own copy holds the TypeScript server too](../specs/decisions/037-own-typescript-server.md)
