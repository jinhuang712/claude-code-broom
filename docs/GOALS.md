# Goals

## Goals

- Claude's work comes out formatted, lint-clean and type-correct by the project's own rules, without anyone
  asking.
- A repo with no tooling gets working tooling in one short conversation (`/broom:setup`).
- Claude sees its mistakes as it edits, through language servers.
- Doing nothing costs close to nothing.

## Non-goals

- **Replacing pre-commit, lefthook or CI.** broom looks after Claude's work. Your own commits and your CI stay
  yours.
- **Being a linter or a formatter.** broom runs existing ones.
- **Imposing a style.** Defaults exist only where a project has none.
- **Running tests.** Too slow for a commit check; CI runs them.
- **Working with other plugins.** broom stands alone.

## What success looks like

- In a legacy repo, no old warning ever blocks Claude.
- A false positive costs one round, never a loop.
- Setup takes at most four questions.
- An idle hook costs about 15 ms; a commit check, a second or two.
