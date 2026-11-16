# Install

3 things must be in place first:

- Claude Code 2.1.271 or later. The language servers are tested on 2.1.280, and Swift's on 2.1.283.
- Python 3.9 or later as `python3`. macOS's system Python works.
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
| TS/JS | `npm i -D oxlint oxlint-tsgolint oxfmt` in the project · `npm i -g typescript-language-server` |
| Rust | `rustup component add clippy rustfmt rust-analyzer` |
| Python | `brew install ruff` · `npm i -g pyright` |
| CSS · SCSS · Less | `npm i -D stylelint` in the project · `stylelint-config-recommended-scss` for SCSS · `stylelint-config-recommended-less` for Less · `npm i -g vscode-langservers-extracted` |
| Swift | Xcode 16+ or a Swift 6+ toolchain · `brew install swiftlint` |
| Duplicate and dead code | `npm i -g jscpd` at version 5 or later |

Tools install machine-wide once. A gap the user leaves alone isn't raised again in any repo.

---

## Other language-server plugins

Don't also enable `gopls-lsp` · `typescript-lsp` · `rust-analyzer-lsp` · `pyright-lsp` · `swift-lsp`. broom's servers already do what they do. When two plugins serve the same files, only one language server starts. `broom doctor` says when that happens.

---

## Commits made outside Claude

Commits made by a wrapper script or by hand skip Claude Code's commit hook. Run `broom install-hook` in the repo to add git's own pre-commit hook for those.

---

## Update

Run `claude plugin marketplace update claude-code-broom && claude plugin update broom@claude-code-broom`.

---

## Remove

Run `claude plugin uninstall broom@claude-code-broom`.
