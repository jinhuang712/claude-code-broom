# broom — Proposal

> Autonomous code hygiene for Claude Code.

---

## In short

Claude finishes a change in minutes. The formatter, the linter and the type checker of the project hear of it only when CI runs or a reviewer reads it. broom is one plugin that holds Claude's changes to the project's own rules before they leave the session.

---

## Why it should exist

Claude writes code quickly, and nothing holds that code to the project's formatter, linter and type checker until CI or a human reviewer does. The pieces to fix that exist, but they don't add up.

---

### Pain points

---

#### Claude sees no type errors from a language server

Claude Code runs language servers only when a plugin declares them. The official TypeScript plugin wraps `typescript-language-server`. TypeScript 7 no longer ships `tsserver`, and its own `tsc --lsp` sends diagnostics only on request, which Claude Code never makes.

---

#### A lint after every edit pushes Claude into early fixes

A hook that lints after every edit is slow and noisy. A warning in the middle of a change makes Claude fix what the next edit would have settled.

---

#### A hook with no tools behind it does nothing, quietly

Many repos have no formatter config, or the tools aren't installed. Any hook then does nothing and says nothing.

---

#### A legacy repo buries a small change under old warnings

Checking whole files reports every old warning beside the one the change added. Across six of the author's repos, 20 to 265 source files sit over 400 lines.

---

## The idea

One plugin does three things:

1. **Set up**: It detects what a repo needs, then installs and configures it with the user's consent.
2. **Sweep**: At the right moments it formats, lints and type-checks Claude's changes, and holds them back until they're clean.
3. **See**: It declares language servers so Claude gets diagnostics as it edits.

---

## What we want

4 wants:

- **Clean work without asking**: Claude's work comes out formatted, lint-clean and type-correct by the project's own rules.
- **Tooling in one conversation**: A repo with no tooling gets working tooling in one short conversation.
- **Mistakes seen while editing**: Claude sees its mistakes as it edits, through language servers.
- **Nothing to pay when idle**: Doing nothing costs close to nothing.

---

## What we don't want

5 things the project refuses to become:

- **A replacement for pre-commit, lefthook or CI**: broom looks after Claude's work, and the user's own commits and CI stay theirs.
- **A linter or a formatter**: broom runs existing ones.
- **A style**: Defaults exist only where a project has none.
- **A test runner**: Tests are too slow for a commit check, and CI runs them.
- **A part of another plugin**: broom stands alone.

---

## Who it is for

A developer who lets Claude Code change a repo and wants those changes to meet the repo's rules without watching each one.
