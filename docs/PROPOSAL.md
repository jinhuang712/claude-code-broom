# broom — Proposal

> A ruler for code quality in Claude Code, and a tool for refactoring.

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

#### Small smells pile up into rot

A repo doesn't rot in a day. Each smell was cheap to fix on the day it appeared, and nobody fixed it. In one repo a function already past the hard limit grew a line at a time, and each line was let through with a reason.

---

#### Nobody can say what was let through

A finding that passes on a second try leaves no reason, and a finding that was fixed leaves no trace. So nobody can say whether the checks work.

---

#### An old repo has no numbers to plan a refactor from

A refactor of a repo that was never held to a bar starts blind: where the smells are, which files cost most and whether the work paid off are all guesses.

---

#### Every session writes its own script to count things

To learn how long the files are, which tests are skipped or what nothing uses, a session writes a throwaway script. The next session writes it again, a little differently, and the two answers don't match. A review of broom itself wrote one such script to count suppressions, skipped tests, TODOs and churn.

---

## The idea

One plugin does three things:

1. **Set up**: It detects what a repo needs, then installs and configures it with the user's consent.
2. **Sweep**: At the right moments it formats, lints and type-checks Claude's changes, and holds them back until they're clean.
3. **See**: It declares language servers so Claude gets diagnostics as it edits.

Around these three it holds one bar for code smells. Each change is measured against the bar while it is made, and a whole repo is measured against it when someone plans a refactor.

---

## What we want

9 wants:

- **Clean work without asking**: Claude's work comes out formatted, lint-clean and type-correct by the project's own rules.
- **Tooling in one conversation**: A repo with no tooling gets working tooling in one short conversation.
- **Mistakes seen while editing**: Claude sees its mistakes as it edits, through language servers.
- **Nothing to pay when idle**: Doing nothing costs close to nothing.
- **A ruler in everyday work**: Every change is measured against one bar for smells, so the code doesn't get worse as it grows.
- **Clean as you go**: A smell is cleaned when it appears, before many of them become rot.
- **A tool for refactoring**: A whole repo gets a full diagnosis, with the data a refactor is planned from and judged by.
- **Nothing passes silently**: A finding is fixed, or it leaves a reason the user can see.
- **No script to write**: A session with broom installed asks broom for a repo's numbers, from line counts to tests to rot.

---

## What we don't want

5 things the project refuses to become:

- **A replacement for pre-commit, lefthook or CI**: broom looks after Claude's work, and the user's own commits and CI stay theirs.
- **A linter or a formatter**: broom runs existing ones.
- **A style**: Defaults exist only where a project has none.
- **A test runner**: Tests are too slow for a commit check, and CI runs them. broom reads the coverage report a project's own run wrote.
- **A part of another plugin**: broom stands alone.

---

## Who it is for

A developer who lets Claude Code change a repo and wants those changes to meet the repo's rules without watching each one. The same developer, the day they take over an old repo and plan its refactor.

---

## Risks

3 risks:

- **Noise teaches Claude to override broom**: Only what a change made worse counts, and a rule nobody fixes stops interrupting.
- **A wrong finding holds good work back**: A false positive costs one round.
- **broom grows heavier than what it guards**: It runs existing tools, and what the record shows as unused is cut.
