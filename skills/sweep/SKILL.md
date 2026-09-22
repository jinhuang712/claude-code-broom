---
name: sweep
description: Sweep code with broom on request - format, lint and type-check a scope the user describes in their own words (uncommitted changes, what's staged, the last few commits, this branch, some folders, or the whole repo) and report what is left. Use for /broom:sweep, or when asked to clean up, format, lint or check code.
argument-hint: "[what to sweep, in your words]"
---

Turn the request (`$ARGUMENTS`, or the conversation) into a `broom sweep` command and run it from the repo root.

| The user says | Command |
|---|---|
| nothing, "my changes", "what I'm working on" | `broom sweep` |
| "what I staged", "what's about to be committed" | `broom sweep --staged` |
| "the last commit", "the last 3 commits" | `broom sweep --base HEAD~1`, `broom sweep --base HEAD~3` |
| "since <commit or tag>" | `broom sweep --base <rev>` |
| "this branch", "my PR" | `broom sweep --base "$(git merge-base HEAD <default branch>)"` |
| "the whole repo", "everything" | `broom sweep --all` |
| "src/api", "these files" | add the paths to any of the above |
| "just check", "don't change anything" | add `--check` |
| "including the ones we accepted" | add `--include-known` |

- The default branch is usually `main`; check with `git symbolic-ref refs/remotes/origin/HEAD` when unsure.
- Every scope formats its files except `--all`, which only reports: formatting a whole repo makes a large diff.
  Run `broom sweep --all --fix` only after the user confirms they want every file reformatted.
- Lint findings count only on the lines in scope (with `--all`, every line); compile and type errors count
  anywhere. Issues accepted earlier stay hidden, and the output says how many.
- Relay the report grouped as printed. Fix the findings only if the user asked for fixes.
- If it reports missing tools, offer /broom:setup.
