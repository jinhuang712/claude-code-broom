---
name: status
description: Show how broom stands in this repo, and set up what is missing on one yes. Says which checks protect the repo and which don't, installs the missing tools and adds configs once the user agrees, and reports what broom stopped, fixed and let through lately. It runs no linter - how the code itself is doing is /broom:scan's. Use for /broom:status, when the user asks what broom is doing here or what it has done, or before work starts in a repo new to broom.
argument-hint: "[how many days of history, 7 by default]"
---

The user ran this command to learn how broom stands in this repo and to have it ready. It is about broom, not
about the code: run no linter and no scan here. Get every number from broom, and write no script.

## 1. Look

```bash
broom doctor --json
```

`healthy` says whether anything is missing. `items` lists each tool and config with its status; one with
`answered: true` is a kind of gap the user already left alone somewhere, so leave it out unless they ask for
everything. `fix_global` and `configure_global` hold the commands that close the gaps, with JS/TS tools installed
once for every repo.

## 2. Set up, on one yes

Skip this step when `healthy` is true.

Otherwise say in a few lines what you would do: the tools to install (`fix_global`, which can hold
`broom install-hook` and a `claude plugin disable …` for a plugin that serves the same files) and the configs to
add (`configure_global`). Then ask one question with AskUserQuestion: set all of it up now (recommended), let me
pick, or not now. Ask nothing else, and no setting.

- **All of it**: run each command from the repo root, one at a time, and stop on a failure. `broom init` never
  edits a file that exists: for a `pyproject.toml` without ruff settings it prints the block to add, and you add
  it as printed. `xcode-select --install` opens macOS's installer and returns at once: ask the user to finish it.
  Run `broom setup --done` afterwards.
- **Let me pick**: go on as `/broom:setup` does from its step 2.
- **Not now**: run `broom setup --dismiss`, and go on with the gaps left.

A plugin disabled here applies after `/reload-plugins`: tell the user so.

## 3. Read the record

```bash
broom doctor --checks
broom report --days 7
broom known
```

Use the days the user gave in place of 7. `broom report` says when nothing was recorded yet: a repo new to broom
has no history. `broom known` lists the findings that were accepted, each with its reason.

## 4. Sum up

Answer in a short reply, not in the commands' output. Three parts, each a few lines:

1. **What protects the repo**: the checks that run, and the ones that don't with why. Name what step 2 set up.
2. **What broom did lately**: blocked, fixed and let through, the fix rate, and the rules let through most often.
   A rule let through far more often than fixed is noise: name it. Say how many findings stand accepted, and the
   reasons that repeat.
3. **What to do next**: up to three steps, such as a gap left on purpose, a limit to move in `.broom.json` for
   code that is deliberate, or `/broom:scan` to see how the code itself is doing.

Start nothing of part 3 yourself: a scan or a settings change waits for the user's go-ahead.
