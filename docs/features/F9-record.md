# F9: Record

```
F9: Record
├── F9.1: Ledger — every block, fix, pass and skip leaves a line
├── F9.2: Turn summary — the user sees what was let through
├── F9.3: Report — what broom stopped, what was fixed and what passed
├── F9.4: Tiers by fix rate — a rule nobody fixes stops interrupting
└── F9.5: /broom:status — how broom stands in a repo, set up on one yes
```

The record says what broom did with each finding. The user ends up knowing whether broom works: how much it stopped, how much of that was fixed and what went through with which reason.

- **Stance**: [Say what happened](../PHILOSOPHY.md#what-happens-to-what-was-skipped)

---

## F9.1: Ledger

Every block, fix, pass and skip is written as one line: when, which repo, which rule, which file and how it ended. A repo and its linked worktrees share one record.

A finding counts as fixed when it was blocked and is gone from a later check that covered its file with its tool. A commit of other files fixes nothing, and neither does a run where the tool was skipped.

The ledger also notes how many seconds each check took, and each time a hook failed and let the action through. It keeps 90 days and at most 2 MB.

- **How it works**: [Record](../specs/record.md)

---

## F9.2: Turn summary

When a turn let something through, the user sees one line at its end, such as `broom let 3 through this turn: 2 bool_params (gave-up), 1 function_lines (accepted: <why>)`. A turn that let nothing through says nothing more than before.

2 gaps:

- With `check_on` at `commit`, no summary is shown.
- What git's own pre-commit hook let through is recorded and not shown.

- **How it works**: [Record](../specs/record.md)

---

## F9.3: Report

`broom report` prints the record of a repo over a period: findings blocked, fixed and let through with the fix rate, then the same per rule, the skips by tool and the seconds a check takes at a commit and at a turn's end. It covers 30 days and this repo unless told otherwise. `--since` starts the period on a day, such as the day a rule changed.

`--all` covers every repo but those in a temporary folder, where only a test or a trial puts one, and says how many it left out.

A finding counts once, however often it was blocked. Notes told without a block are recorded and not yet shown.

- **Commands**: [broom report](../CLI.md#broom-report)
- **How it works**: [Record](../specs/record.md)

---

## F9.4: Tiers by fix rate

A rule that is let through far more often than it is fixed is told to Claude without stopping the turn. The user is told when a rule changes tier. A rule that is nearly always fixed stays as it is.

It applies to hints only. A type error and a severe smell never change tier.

- **Design**: [6. A finding ends fixed or with a reason the user sees](../DESIGNS.md#6-a-finding-ends-fixed-or-with-a-reason-the-user-sees)

---

## F9.5: /broom:status

`/broom:status` tells the user how broom stands in a repo and gets it ready, in one command. It is about broom: how the code is doing is `/broom:scan`'s. The user types no `broom` command.

It goes in 4 steps:

1. It looks at what the repo lacks: tools, configs and git's hook.
2. When something is missing, it says what it would install and add, and asks one question: all of it, let me pick, or not now.
3. It reads the record: the checks that run, what broom stopped, fixed and let through in the last 7 days, and the findings accepted with their reasons.
4. It sums up what protects the repo and what broom did, with up to three next steps.

It runs no linter and measures no code. It starts no scan and changes no setting: those wait for the user's go-ahead. A repo new to broom has no history yet, and the summary says so. A number of days given after the command replaces the 7.

- **Stance**: [Ask, don't assume](../PHILOSOPHY.md#who-decides-what-is-installed-or-changed)
- **Design**: [7. Nothing is installed or set without a yes](../DESIGNS.md#7-nothing-is-installed-or-set-without-a-yes)
- **Commands**:
  - [broom doctor](../CLI.md#broom-doctor)
  - [broom report](../CLI.md#broom-report)
  - [broom known](../CLI.md#broom-known)
- **Why**: [035: Three commands, and a cleanup that is none](../specs/decisions/035-three-commands.md)

**Stories** (1):

- A user about to work in a complex repo runs it once to get the repo ready, and again a week later to see what broom stopped.
