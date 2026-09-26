# broom 🧹

**Autonomous code hygiene for Claude Code.** broom sets up the formatters, linters, type checkers and language
servers a repo needs, then sweeps Claude's work when it should: formatted, lint-clean and type-correct, by the
project's own rules.

[中文](docs/README.zh-CN.md)

## What it does

- **Sets up.** When you open a session in a repo, broom notices what's missing and Claude offers to install and
  configure it. Nothing is installed without your yes.
- **Sweeps.** When it should, broom formats, lints and type-checks Claude's changes, and holds them back until
  they're clean.
- **Sees.** Language servers for Go, TS/JS, Rust, Python and CSS (with SCSS and Less) give Claude diagnostics as it
  edits.

It uses your project's own tools and configs, only looks at what changed, and never blocks twice on the same
result.

```text
[broom] Commit blocked: 2 issue(s) in the files being committed. Fix them and commit again. If one is
pre-existing or a false positive, say so and run the same commit again: broom lets an unchanged result through.

oxlint (~/code/app):
  src/api/client.ts:42:5  typescript(no-floating-promises)  Promises must be awaited
tsc (~/code/app):
  src/pages/home.tsx:17:9  TS2345  Argument of type 'string' is not assignable to 'number'  [not in the changed files]
```

## Install

**Requirements:** Claude Code 2.1.271 or later (the language servers are tested on 2.1.280), Python 3.9+ as
`python3` (macOS's system Python works), and git.

1. Add the marketplace and install the plugin, inside Claude Code:

   ```text
   /plugin marketplace add jinhuang712/claude-code-broom
   /plugin install broom@claude-code-broom
   ```

   or from a shell:

   ```bash
   claude plugin marketplace add jinhuang712/claude-code-broom
   claude plugin install broom@claude-code-broom
   ```

2. Start a session in a repo. If anything is missing, Claude offers `/broom:setup`; accept, or run it yourself.
   It asks up to four questions, installs what you pick, and checks the result. You set up once: tools install
   machine-wide, settings are user settings, and a gap you leave alone isn't raised again in any repo. A new
   repo only asks about kinds of gap you haven't answered yet (usually just its missing formatter config).

3. Optional: adjust the settings in `/config`.

If you'd rather install the tools yourself, these are the ones broom uses:

| Language | Install |
|---|---|
| Go | `brew install golangci-lint` · `go install golang.org/x/tools/gopls@latest` |
| TS/JS | `npm i -D oxlint oxlint-tsgolint oxfmt` in the project · `npm i -g typescript-language-server` (the language server) |
| Rust | `rustup component add clippy rustfmt rust-analyzer` |
| Python | `brew install ruff` · `npm i -g pyright` |
| CSS, SCSS, Less | `npm i -D stylelint` in the project, plus `stylelint-config-recommended-scss` for SCSS or `stylelint-config-recommended-less` for Less · `npm i -g vscode-langservers-extracted` |

Don't also enable `gopls-lsp`, `typescript-lsp`, `rust-analyzer-lsp` or `pyright-lsp`: broom's servers already do
what they do (for TypeScript, the same typescript-language-server, with the project's TypeScript), and when two
plugins serve the same files, only one language server starts. `broom doctor` tells you if that happens.

**Update:** `claude plugin marketplace update claude-code-broom && claude plugin update broom@claude-code-broom`
**Remove:** `claude plugin uninstall broom@claude-code-broom`

## Use

Mostly, you don't: broom sweeps on its own. When you want a look first, ask for a sweep in your own words:

```text
/broom:sweep
/broom:sweep what I staged
/broom:sweep the last 3 commits
/broom:sweep the whole repo
```

| Setting | Default | Choices |
|---|---|---|
| `format_on` | `commit` | `edit` (also after every edit), `off` |
| `check_on` | `commit` | `stop` (also at every turn end), `off` |
| `format_scope` | `changed` | `function` (whole changed functions; in CSS, rules), `file` |

A `.broom.json` at the repo root overrides these for one repo and can exclude paths:

```json
{ "format_scope": "function", "exclude": ["vendor/**", "**/*.pb.go"] }
```

The `broom` command is on the PATH too: `broom sweep`, `broom doctor`, `broom known`. See [Features](docs/FEATURES.md).

## Docs

[Philosophy](docs/PHILOSOPHY.md) · [Goals](docs/GOALS.md) · [Proposal](docs/PROPOSAL.md) ·
[Design](docs/DESIGN.md) · [Features](docs/FEATURES.md) · [Changelog](CHANGELOG.md)

## Develop

`python3 -m unittest discover -s tests` · `claude plugin validate .` · standard library only, Python 3.9+

## License

[MIT](LICENSE)
