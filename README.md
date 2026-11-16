# broom 🧹

> Autonomous code hygiene for Claude Code.

broom holds Claude's changes to the project's own formatter, linter and type checker before they leave the session. It judges only what a change made worse, so a legacy repo's old warnings never land on a small fix.

[中文](docs/README.zh-CN.md)

---

## What it does

- 🧰 **Sets up**: When a session opens in a repo, broom notices what's missing and Claude offers to install and configure it.
- 🧹 **Sweeps**: It formats, lints and type-checks Claude's changes at a commit and at a turn's end, and holds them back until they're clean.
- 👃 **Smells**: A change that makes a function, a file or a type too long, nests too deep or repeats code gets a hint past the soft limit and a block past the hard one.
- 👀 **Sees**: Language servers for Go, TS/JS, Rust, Python, Swift and CSS give Claude diagnostics as it edits.

Nothing is installed without the user's yes. The same lint result never blocks twice, and a type error passes fixed or accepted with a reason on record.

---

## Install

```text
/plugin marketplace add jinhuang712/claude-code-broom
/plugin install broom@claude-code-broom
```

It needs Claude Code 2.1.271 or later, Python 3.9+ as `python3`, and git. [INSTALL.md](docs/INSTALL.md) has the rest: the shell way, the tools per language, updating and removing.

---

## How to use

Start a session in a repo. When a tool or a config is missing, Claude offers `/broom:setup`, which asks at most two questions.

Then let Claude work. When it commits a change that breaks a rule, the commit is held back with a report:

```text
[broom] Commit blocked: 2 issue(s) in the files being committed, 1 of them type or compile errors, which don't
pass on a retry. Fix them and commit again. If they predate this change or are false positives, run
`broom known --accept "<why>"`, then commit again.

oxlint (~/code/app):
  src/api/client.ts:42:5  typescript(no-floating-promises)  Promises must be awaited
tsc (~/code/app):
  src/pages/home.tsx:17:9  TS2345  Argument of type 'string' is not assignable to 'number'  [not in the changed files]
```

Claude fixes the findings and commits again. To look first, ask for a sweep in your own words:

```text
/broom:sweep what I staged
/broom:sweep the last 3 commits
```

To pay down what's already there, ask for `/broom:clean`, which ranks the code smells worst first and cleans up in small, tested batches.

---

## Configuration

Four settings in `/config` start at defaults and are never asked. A `.broom.json` at the repo root overrides them for one repo, excludes paths and moves the smell limits. [F7: Settings](docs/features/F7-settings.md) lists them.

---

## Docs

- [PROPOSAL.md](docs/PROPOSAL.md) says why broom exists.
- [PHILOSOPHY.md](docs/PHILOSOPHY.md) holds its stances.
- [DESIGNS.md](docs/DESIGNS.md) holds the commitments every design must meet.
- [FEATURES.md](docs/FEATURES.md) lists what it does.
- [CLI.md](docs/CLI.md) describes the `broom` command.
- [INSTALL.md](docs/INSTALL.md) covers installing, updating and removing.
- [GLOSSARY.md](docs/GLOSSARY.md) fixes the terms.
- [ARCHITECTURE.md](docs/specs/ARCHITECTURE.md) maps the parts.
- [GOALS.md](docs/plan/GOALS.md) holds what is checked.
- [ROADMAP.md](docs/plan/ROADMAP.md) says what comes next.
- [ISSUES.md](docs/plan/ISSUES.md) and [TODO.md](docs/plan/TODO.md) hold the open work and the open questions.
- [CONTRIBUTING.md](docs/CONTRIBUTING.md) says how to change broom.
- [AGENTS.md](AGENTS.md) holds the rules for agents that work on it.
- [CHANGELOG.md](CHANGELOG.md) lists each release.

---

## License

[MIT](LICENSE)
