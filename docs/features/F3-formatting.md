# F3: Formatting

```
F3: Formatting
├── F3.1: When to format — at commit, after every edit, or never
└── F3.2: How much to format — the scope
    ├── F3.2.1: changed
    ├── F3.2.2: function
    └── F3.2.3: file
```

broom formats Claude's changes with the project's own formatter. JS/TS, CSS, Python and Swift are formatted only where a formatter is configured.

---

## F3.1: When to format

The `format_on` setting says when. At `commit`, the default, the files a commit takes are formatted and staged again. At `edit`, each file is also formatted after every edit. At `off`, nothing is formatted.

A formatter's rewrite reaches Claude as the diff Claude Code shows of a changed file. An idle edit hook costs one Python start, 30 to 45 ms measured on macOS.

- **Stance**: [The project's tools, not ours](../PHILOSOPHY.md#whose-rules-decide-what-is-clean)
- **How it works**: [Commit check](../specs/commit-check.md) · [Format scopes](../specs/format-scopes.md)

---

## F3.2: How much to format

The `format_scope` setting says how much of a file the formatter may change.

- **Stance**: [Only what changed](../PHILOSOPHY.md#how-much-of-the-code-does-a-check-judge)
- **Commands**: [broom fmt](../CLI.md#broom-fmt)
- **How it works**: [Format scopes](../specs/format-scopes.md)

---

### F3.2.1: changed

Only the formatter's edits on changed lines are kept. This is the default, and it works with every formatter.

---

### F3.2.2: function

The whole of each changed function is formatted. In CSS that is the innermost rule, and in Swift a computed property counts too. When no language server answers, it falls back to `changed` with a note.

---

### F3.2.3: file

The whole file is formatted.
