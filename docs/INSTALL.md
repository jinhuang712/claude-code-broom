# Install

4 things must be in place first:

- macOS, where broom is developed and tested. Linux has what broom needs and has not been run. Windows is not supported: broom locks files and ends process groups in ways only those two have.
- Claude Code 2.1.271 or later. The language servers are tested on 2.1.280, and Swift's on 2.1.283.
- Python 3.9 or later as `python3`. macOS's system Python works: the test suite passed on its 3.9.6 on 2026-11-17.
- git.

---

## From inside Claude Code

1. Add the marketplace with `/plugin marketplace add jinhuang712/claude-code-broom`.
2. Install the plugin with `/plugin install broom@claude-code-broom`.
3. Start a session in a repo.

When the repo lacks a tool or a config, Claude offers `/broom:setup`. It asks at most two questions: whether to install the missing tools, and whether to add formatter configs. It installs what the user picks and checks the result.

To check that it worked, run `broom doctor` in the repo. It lists each language with its tools and says what is missing.

---

## From a shell

1. Run `claude plugin marketplace add jinhuang712/claude-code-broom`.
2. Run `claude plugin install broom@claude-code-broom`.

To check that it worked, start a session in a repo and run `broom doctor`.

---

## The tools, by hand

A user who would rather install the tools themselves needs these:

| Language | Install |
|---|---|
| Go | `brew install golangci-lint` · `go install golang.org/x/tools/gopls@latest` |
| TS/JS | `npm i -D oxlint oxlint-tsgolint oxfmt` in the project · the command `broom doctor` gives for broom's own copy |
| Rust | `rustup component add clippy rustfmt rust-analyzer` |
| Python | `brew install ruff` · `npm i -g pyright` |
| CSS · SCSS · Less | `npm i -D stylelint` in the project · `stylelint-config-recommended-scss` for SCSS · `stylelint-config-recommended-less` for Less · `npm i -g vscode-langservers-extracted` |
| Swift | Xcode 16+ or a Swift 6+ toolchain · `brew install swiftlint` |
| Duplicate and dead code | `npm i -g jscpd` at version 5 or later |

Tools install machine-wide once. A gap the user leaves alone isn't raised again in any repo.

---

## Other language-server plugins

Don't also enable a plugin whose language server serves Go, TS/JS, Rust, Python, Swift or CSS files, such as these 5: `gopls-lsp` · `typescript-lsp` · `rust-analyzer-lsp` · `pyright-lsp` · `swift-lsp`. broom's servers already do what they do. When two plugins serve the same files, only one language server starts. `broom doctor` names each such plugin, and `/broom:setup` offers to disable it.

---

## Commits made outside Claude

Commits made by a wrapper script or by hand skip Claude Code's commit hook. Run `broom install-hook` in the repo to add git's own pre-commit hook for those.

---

## Update

Run `claude plugin marketplace update claude-code-broom && claude plugin update broom@claude-code-broom`.

---

## Remove

Run `claude plugin uninstall broom@claude-code-broom`.
