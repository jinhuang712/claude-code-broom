# Designs

Claude's edits, commits and turn ends go in. Formatted files, a block with a report or a short message come out. Between the two sit hooks that start, run the project's tools on what changed and exit. Beside the hooks sits the `broom` command, which Claude runs to measure a repo and which never blocks.

broom is designed around 8 guidelines:

1. **Only Claude Code's plugin parts and Python's standard library**: Nothing runs between hooks, and nothing is installed beyond the tools themselves.
2. **An idle hook exits in milliseconds**: A hook with nothing to do costs a process start.
3. **A hook run ends within 30 seconds**: A slow tool is cut off, never waited for.
4. **A finding counts only where the change made things worse**: Old code a change doesn't touch never comes up.
5. **A tool that is missing or fails never blocks**: The check goes ahead without it and says so.
6. **A finding ends fixed or with a reason the user sees**: Nothing is waved through, and nothing traps Claude for good.
7. **Nothing is installed or set without a yes**: A hook tells Claude, and Claude asks the user.
8. **A repo's config holds choices, never commands**: Honoring it in an untrusted repo is safe.

---

## 1. Only Claude Code's plugin parts and Python's standard library

broom is built from hooks, skills, settings, `bin/` and `.lsp.json`, on Python 3.9 with no package beyond the standard library. A user installs the plugin and the tools their languages need, and nothing else. The cost is that every hook starts cold and state lives in files that many hooks share.

**Ask**: Does it need a process that outlives the hook, or a package the user must install for broom itself?

- **Stance**: [At three moments of Claude's flow](PHILOSOPHY.md#when-may-a-check-interrupt)
- **Decisions**:
  - [001: One plugin of its own](specs/decisions/001-own-plugin.md)
- **How it works**:
  - [Hook limits](specs/hook-limits.md)

---

## 2. An idle hook exits in milliseconds

Every Bash call, edit and turn end starts a hook, and most have nothing to check. The cost is a prefilter in shell before Python starts, and settings read from the environment instead of a file.

**Ask**: What does it cost on a call where it has nothing to do?

- **Stance**: [At three moments of Claude's flow](PHILOSOPHY.md#when-may-a-check-interrupt)
- **Decisions**:
  - [002: The commit hook reads every Bash call](specs/decisions/002-every-bash-call.md)
- **How it works**:
  - [Commit check](specs/commit-check.md)

---

## 3. A hook run ends within 30 seconds

A hook that runs long makes the session feel stuck, and a tool left compiling takes the cores from the work in front. The cost is that a slow tool's findings are lost for that run, so a cold build may go unchecked until its caches are warm.

**Ask**: What does it start, and what ends it when the time is up?

- **Stance**: [At three moments of Claude's flow](PHILOSOPHY.md#when-may-a-check-interrupt)
- **Decisions**:
  - [024: Tools are kept to a quarter of the cores](specs/decisions/024-thread-caps.md)
  - [025: A command writes to files](specs/decisions/025-files-not-pipes.md)
  - [026: A hook run is cut at 30 seconds](specs/decisions/026-thirty-second-hook.md)
- **How it works**:
  - [Hook limits](specs/hook-limits.md)

---

## 4. A finding counts only where the change made things worse

A legacy repo holds more old warnings than any change adds, and noise teaches Claude to override broom. The cost is what a change breaks elsewhere without touching it: an export that a change left unused is missed. Type and compile errors are the one exception, since a changed signature breaks callers in files nobody touched.

**Ask**: Would it report something in code the change left as it was?

- **Stance**: [Only what changed](PHILOSOPHY.md#how-much-of-the-code-does-a-check-judge)
- **Decisions**:
  - [006: A smell counts when the change pushed it past a limit](specs/decisions/006-made-worse.md)
  - [028: A change is told the old smells in the code it touches](specs/decisions/028-old-smells-in-touched-code.md)
  - [007: A renamed file is measured against its old path](specs/decisions/007-renames-and-imports.md)
  - [009: An occurrence counts when the change raises the count](specs/decisions/009-occurrence-by-count.md)
  - [013: Dead code counts on added lines](specs/decisions/013-dead-code-added-lines.md)
- **How it works**:
  - [What counts](specs/what-counts.md)
  - [Smells](specs/smells.md)

---

## 5. A tool that is missing or fails never blocks

A check that can't run isn't Claude's mistake. The cost is that a missing tool lets through what it would have found, so every skip is said in a note and content checked with a skip is never recorded as passed.

**Ask**: What happens to the commit when its tool is missing, times out or crashes?

- **Stance**: [Say what happened](PHILOSOPHY.md#what-happens-to-what-was-skipped)
- **How it works**:
  - [Hook limits](specs/hook-limits.md)

---

## 6. A finding ends fixed or with a reason the user sees

A linter can be wrong, an issue can predate the change, and a refactor can belong to a later step. So every finding that is more than slight passes fixed, or accepted with one command and a reason, and the reason reaches the user. Trying again is no way out, at a commit or at a turn's end. Where no way out is left, broom lets go after three blocks and tells the user what is still open. The cost is more rounds for each task, and one more step for a finding that was wrong.

**Ask**: Can Claude get past it without a fix or a reason the user sees?

- **Stance**: [Fixed, or let through with a reason the user sees](PHILOSOPHY.md#how-does-a-finding-end)
- **Decisions**:
  - [003: Every finding passes fixed or accepted with a reason](specs/decisions/003-reason-for-every-pass.md)
  - [031: Trying again passes nothing, and three blocks end in a loud give-up](specs/decisions/031-no-pass-on-a-second-try.md)
  - [016: A smell past the hard limit blocks like a type error](specs/decisions/016-severe-smells.md)
- **How it works**:
  - [Commit check](specs/commit-check.md)
  - [Turn end](specs/turn-end.md)

---

## 7. Nothing is installed or set without a yes

The machine and the repo are the user's. Hooks can't ask, so they tell Claude, and Claude asks. The cost is one conversation before a repo with gaps is fully checked.

**Ask**: Does it change the user's machine, repo or settings before they agreed?

- **Stance**: [Ask, don't assume](PHILOSOPHY.md#who-decides-what-is-installed-or-changed)
- **Decisions**:
  - [018: broom offers a cleanup and never starts one](specs/decisions/018-offer-cleanup.md)
  - [022: Setup answers are remembered by kind](specs/decisions/022-answers-by-kind.md)
  - [029: A tool broom can do without is listed and never asked for](specs/decisions/029-optional-tools.md)
  - [030: Known vulnerabilities are looked up only on request](specs/decisions/030-vulnerabilities-on-request.md)
- **How it works**:
  - [Setup](specs/setup.md)

---

## 8. A repo's config holds choices, never commands

`.broom.json` comes with the repo, and a repo can come from anyone. It holds settings, limits and path globs. The cost is that a project can't hand broom a command of its own to run.

**Ask**: Could a line in a repo's config make broom run something?

- **Stance**: [The project's tools, not ours](PHILOSOPHY.md#whose-rules-decide-what-is-clean)
- **How it works**:
  - [Settings](specs/settings.md)
