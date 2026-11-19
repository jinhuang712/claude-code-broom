# F1: Setup

```
F1: Setup
├── F1.1: Doctor — what a repo needs and has
├── F1.2: Offer at session start — Claude offers a setup when a repo has gaps
├── F1.3: /broom:setup — at most two questions, then install and verify
├── F1.4: Default configs — added where a project has none
└── F1.5: Protection list — which checks run and which don't
```

Setup gets a repo the formatters, linters, type checkers and language servers it needs. The user ends up with tools that run and configs that exist. Nothing is installed without their yes.

---

## F1.1: Doctor

`broom doctor` lists a repo's languages with their tools and configs, and gives a ready command for each fix.

It checks 10 things:

- Each needed tool is on PATH and runs.
- The TypeScript language server starts and gives Claude diagnostics, and broom's own copy is the fix.
- The project's configured tools resolve, or its dependencies need installing.
- Formatter configs exist, with one fix at the root of a monorepo.
- Tracked CSS, SCSS and Less files get 3 tools checked: linter · formatter · language server.
- Swift files get the same, in SwiftPM packages and Xcode projects alike.
- A repo with TS/JS has oxlint at its root, which the smells need whichever linter the projects use.
- A repo with TS/JS has a dependency-cruiser that can read its files, and broom's own copy is the fix.
- No other plugin starts a language server for the same files.
- `.broom.json` is valid.

It looks three levels deep and at up to 20 projects per language. Python files git tracks count as Python also where no project file sits above them. It flags unknown keys and values in `.broom.json`.

After the gaps it lists the optional tools for the repo's languages, each with what it finds and its install command. An optional tool is no gap: it is never offered at session start and never changes the exit code.

- **Design**: [7. Nothing is installed or set without a yes](../DESIGNS.md#7-nothing-is-installed-or-set-without-a-yes)
- **Commands**: [broom doctor](../CLI.md#broom-doctor)
- **How it works**: [Setup](../specs/setup.md)
- **Why**: [029: A tool broom can do without is listed and never asked for](../specs/decisions/029-optional-tools.md)

**Stories** (1):

- A user with a rustup proxy and no clippy component runs the doctor to learn which command installs it.

---

## F1.2: Offer at session start

When a session opens in a repo with gaps, Claude is asked once per session to offer `/broom:setup` at a natural point, and before the first commit at the latest.

A gap of a kind the user already answered, in any repo, stays quiet. When the user declines, Claude runs `broom setup --dismiss`.

The hook takes 0.1 to 0.25 seconds, measured on a 2,376-file repo.

- **Stance**: [Ask, don't assume](../PHILOSOPHY.md#who-decides-what-is-installed-or-changed)
- **Design**: [7. Nothing is installed or set without a yes](../DESIGNS.md#7-nothing-is-installed-or-set-without-a-yes)
- **Commands**: [broom setup](../CLI.md#broom-setup)
- **How it works**: [Setup](../specs/setup.md)
- **Why**: [022: Setup answers are remembered by kind](../specs/decisions/022-answers-by-kind.md)

---

## F1.3: /broom:setup

The skill runs the doctor, asks at most two questions, acts on the answers, verifies and records the decision.

The 2 questions:

1. Whether to install the missing tools.
2. Whether to turn formatting on by adding formatter configs.

Settings aren't asked: they start at defaults. JS/TS and CSS tools install machine-wide by default, with devDependencies as the alternative.

- **Stance**: [Ask, don't assume](../PHILOSOPHY.md#who-decides-what-is-installed-or-changed)
- **Commands**:
  - [broom doctor](../CLI.md#broom-doctor)
  - [broom init](../CLI.md#broom-init)
  - [broom setup](../CLI.md#broom-setup)

---

## F1.4: Default configs

`broom init` adds default configs where a project has none. It never overwrites.

For Swift it adds a `.swift-format` with 4-space indents and 120 columns, where swift-format's own defaults are 2 and 100. For CSS outside JS projects it turns on oxfmt.

- **Stance**: [The project's tools, not ours](../PHILOSOPHY.md#whose-rules-decide-what-is-clean)
- **Commands**: [broom init](../CLI.md#broom-init)

---

## F1.5: Protection list

`broom doctor --checks` lists what protects a repo. Each language the repo has gets a block with one row per check: format · lint · type check · smells · duplicate and dead code · cycles · diagnostics as Claude edits.

A row takes 1 of 3 forms:

- The check runs, with the tool behind it.
- The check doesn't run, with the reason and the command that turns it on.
- broom has no such check for the language, with the reason.

After the languages the list names the gaps of the repo itself, such as a missing git hook, and the smells `.broom.json` turns off one by one. It ends with what broom checks with no tool installed at all. It starts no tool the plain doctor doesn't start, and it exits as the plain doctor does.

- **Stance**: [Say what happened](../PHILOSOPHY.md#what-happens-to-what-was-skipped)
- **Commands**: [broom doctor](../CLI.md#broom-doctor)
- **How it works**: [Setup](../specs/setup.md)
