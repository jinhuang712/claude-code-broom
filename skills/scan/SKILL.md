---
name: scan
description: Scan code with broom and list what it finds, fixing nothing - lint findings, type errors and code smells in a scope the user gives in their own words (the whole repo, a module, some files, the files changed lately, what's staged, a commit or this branch). Use for /broom:scan, or when asked to scan, check, lint or look over the quality of code without changing it.
argument-hint: "[what to scan, in your words]"
---

The user ran this command to see what is wrong, not to have it fixed. Change no file: no edit, no format, no
`broom known --accept`. Get every finding from broom, and write no script. Run the commands from the repo root.

## 1. Pick the scope

Turn the request (`$ARGUMENTS`, or the conversation) into one of two kinds of scan. With no scope given, scan the
whole repo.

An **area** scan lists everything that is there:

| The user says | Commands |
|---|---|
| nothing, "the whole repo", "everything" | `broom sweep --all --check`, then `broom diagnose` |
| "src/api", "this module", "these files" | `broom sweep --all --check <paths>`, then `broom diagnose <paths>` |

A **change** scan lists what a change made worse, and the old smells in the code it touched:

| The user says | Command |
|---|---|
| "my changes", "what I changed lately" | `broom sweep --check` |
| "what I staged", "what's about to be committed" | `broom sweep --check --staged` |
| "the last commit", "the last 3 commits" | `broom sweep --check --base HEAD~1`, `broom sweep --check --base HEAD~3` |
| "commit abc123", "since <commit or tag>" | `broom sweep --check --base abc123~1`, `broom sweep --check --base <rev>` |
| "this branch", "my PR" | `broom sweep --check --base "$(git merge-base HEAD <default branch>)"` |
| any of these "in src/api" | add the paths |

- Always pass `--check`: without it `broom sweep` formats the files.
- A scan from one commit covers every change since it, later commits and uncommitted work included. Say so when the
  user named one commit.
- The default branch is usually `main`; check with `git symbolic-ref refs/remotes/origin/HEAD` when unsure.
- `broom diagnose` measures with no time cut. On a repo of thousands of files say that it takes a while before you
  start it.
- Issues accepted earlier are collapsed: they count in the totals, the output says how many, and no list shows
  them. Add `--include-known` when the user asks to see them.

## 2. Report

Answer in a short reply, not in the commands' output.

1. **What was scanned**: the scope, the kind of scan and how many files.
2. **What was found**, most severe first: type and compile errors, lint findings, smells past the hard limit,
   hints, nits. Give each group its count and its worst places as `file:line`. For an area scan add the hotspot
   files and any check-up counter that stands out.
3. **What wasn't measured**: every tool broom names as missing, since counts without it read as cleaner than the
   code is. Offer `/broom:setup` for them.

When a list is cut short, say how many more there are. `broom diagnose --out <file>` writes the whole report to a
file: offer it, and write it only when the user says so.

Fix nothing, even a finding that would take one line. End by saying that you can fix what they pick, worst first,
and wait for their answer.
