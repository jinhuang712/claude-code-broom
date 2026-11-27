# F2: Sweep

```
F2: Sweep
├── F2.1: Commit check — a git commit is formatted, checked and held back
├── F2.2: Turn-end check — what a turn changed is checked when Claude stops
├── F2.3: Subagent check — a subagent fixes its own work
├── F2.4: git's pre-commit hook — commits Claude Code never sees
│   └── F2.4.1: Offered at setup
├── F2.5: Known issues — what was let through, and why
│   ├── F2.5.1: A reason for every pass
│   ├── F2.5.2: A turn can end with a finding open
│   └── F2.5.3: A standing smell the user keeps — accepted by its place, with their agreement
├── F2.6: Scan on request — a scope in the user's own words, found and not fixed
├── F2.7: Time limit — a hook run takes at most 30 seconds
├── F2.8: Self-waivers shown — a loosened bar never goes unseen
├── F2.9: Messages that say how to fix — the fix beside the finding
├── F2.10: Check after an edit — format and what is judged in milliseconds
├── F2.11: Nothing is waved through — a finding ends fixed or accepted with a reason
├── F2.12: A pass is told to the user — Claude says what it left and why
├── F2.13: A turn that changed code shows that tests ran — or that counts as left over
└── F2.14: Open findings come back — told again until they end
```

A sweep formats, lints and type-checks Claude's changes and holds them back until they're clean. It uses the project's own tools and configs.

Lint findings count on the lines that changed. Type and compile errors count anywhere, and the report marks one outside the change with `[not in the changed files]`. A report lists at most 40 findings, and names the ten most frequent rules when there are more.

---

## F2.1: Commit check

When Claude runs a `git commit`, broom formats the commit's files, lints and type-checks them, and blocks the commit while findings remain.

It reads commands written as `git -C dir commit`, `T=dir; git -C $T commit` and `git add . && git commit`. A partly staged file is left unformatted. A commit with `--no-verify` is not checked.

A Bash call that isn't a commit costs about 13 ms, or about 60 ms when the command mentions git and commit without committing.

- **Design**:
  - [2. An idle hook exits in milliseconds](../DESIGNS.md#2-an-idle-hook-exits-in-milliseconds)
  - [4. A finding counts only where the change made things worse](../DESIGNS.md#4-a-finding-counts-only-where-the-change-made-things-worse)
- **How it works**:
  - [Commit check](../specs/commit-check.md)
  - [What counts](../specs/what-counts.md)
- **Why**: [002: The commit hook reads every Bash call](../specs/decisions/002-every-bash-call.md)

---

## F2.2: Turn-end check

When Claude stops, broom checks the files the turn changed: files Claude edited, files changed since the prompt by any means and files committed after it. It blocks the turn's end while a finding is left, and after three blocks it gives up and tells the user.

A commit made before the prompt is not the turn's, so a pull or a reset to a remote branch brings in no finding. A file Claude edited that git ignores is left out, as one `.broom.json` excludes is.

It applies with `check_on` at `stop`, the default. It waits once for each piece of background work, told apart by its task id: work an earlier turn's end already waited for doesn't hold a later one. A prompt during a wait keeps the waiting turn's changes, which the next checked turn's end checks. A turn in plan mode is not checked. An idle turn end costs one Python start, 30 to 45 ms measured on macOS.

A hint stops the turn here as a block does.

1 gap:

- Another session's commit in the same checkout during the turn counts as the turn's.

- **Design**: [6. A finding ends fixed or with a reason the user sees](../DESIGNS.md#6-a-finding-ends-fixed-or-with-a-reason-the-user-sees)
- **How it works**: [Turn end](../specs/turn-end.md)
- **Why**:
  - [019: The turn-end check waits for background work](../specs/decisions/019-wait-for-background.md)
  - [020: The turn's changes come from a snapshot at the prompt](../specs/decisions/020-turn-snapshot.md)
  - [041: A commit counts as the turn's when it was made after the prompt](../specs/decisions/041-turn-own-commits.md)

**Stories** (1):

- A user who commits by hand still gets Claude's edits checked, at the end of each turn.

---

## F2.3: Subagent check

A subagent's edits are checked at that subagent's end. The block goes to the subagent, which fixes its own work.

- **How it works**: [Turn end](../specs/turn-end.md)
- **Why**: [021: A subagent's end checks its own edits](../specs/decisions/021-subagent-own-end.md)

---

## F2.4: git's pre-commit hook

`broom install-hook` adds git's own pre-commit hook to a repo. It checks the staged files of every commit, a wrapper script's and a person's included, without formatting.

It never replaces another tool's hook and prints the line to add to it instead. That line finds broom the way broom's own hook does, and a commit goes ahead where no broom is found. Once the line is in the hook, `broom doctor` counts the hook as installed. Content that passed already goes through at once. Where it is installed it is the commit check, and the commit check of F2.1 only formats.

- **Commands**: [broom install-hook](../CLI.md#broom-install-hook)
- **How it works**: [Commit check](../specs/commit-check.md)
- **Why**: [004: git's own hook checks without formatting](../specs/decisions/004-git-hook-checks.md)

**Stories** (1):

- A user whose wrapper script commits for them installs the hook, so those commits are checked too.

---

### F2.4.1: Offered at setup

`broom doctor` lists git's hook as a gap in a repo with code that has none, and `/broom:setup` offers it with the missing tools, in the same question. A user who declined once is not asked in the next repo.

---

## F2.5: Known issues

A finding Claude accepted with a reason is known and not raised again until its code changes. It never expires. Known issues live in the repo's `.broom/`, by paths from its root, so one accepted in a linked worktree stays known in the main checkout, where the work lands, and a moved repo keeps them. One accepted before 0.28.1 in a worktree since deleted moves to the main checkout's file the next time `broom known` lists it, once a line of that file proves it is the same finding. `broom known` lists and clears them.

- **Design**: [6. A finding ends fixed or with a reason the user sees](../DESIGNS.md#6-a-finding-ends-fixed-or-with-a-reason-the-user-sees)
- **Commands**: [broom known](../CLI.md#broom-known)
- **How it works**: [What counts](../specs/what-counts.md)
- **Why**:
  - [003: Every finding passes fixed or accepted with a reason](../specs/decisions/003-reason-for-every-pass.md)
  - [046: A known issue never expires](../specs/decisions/046-known-issues-never-expire.md)

---

### F2.5.1: A reason for every pass

A blocked finding passes fixed, or after `broom known --accept "<why>"`, which puts the reason on record. Running the same commit again blocks again. A finding that is wrong costs one command and one sentence. One kind can't be accepted: a function, a type or a file that was already past the hard limit and grew.

`BROOM_NO_ACCEPT=1` turns accepting off, and the block message then stops offering it.

---

### F2.5.2: A turn can end with a finding open

After three blocks broom gives up, since it never traps a turn for good. Nothing becomes known that way: what is left stays open, the user is told in a line that opens `broom GAVE UP`, and the next commit of that file still stops on it.

---

### F2.5.3: A standing smell the user keeps

A smell in code no change touches never blocks, so no block offers to accept it. When the user decides it stays, such as the constants of a published formula, Claude accepts it where `broom smells` lists it:

```
broom known --accept "<why it stays>" --agreed --smell KIND FILE:LINE
```

`--agreed` is required, so Claude accepts a standing smell only once the user agreed. A `FILE` or a folder without a line accepts every smell of that kind there. Each occurrence is accepted on its own: a file with 3 magic numbers keeps 2 after one is accepted.

`broom smells`, `broom diagnose` and the session note collapse it: no list shows it, every total still counts it, and the first line says how many are collapsed. It comes back when its line changes, or when a sized smell's size changes.

2 gaps:

- The session note reads a scan cached by HEAD, so an accept shows there after the next commit.
- `broom report` doesn't show it, since nothing blocked it. `broom known` lists it.

- **Why**: [047: A standing smell is accepted with the user's agreement](../specs/decisions/047-standing-smells-accepted.md)

---

## F2.6: Scan on request

`/broom:scan` runs the tools on a scope the user describes in their own words and lists what it finds. It fixes nothing and formats nothing. With no scope it scans the whole repo.

It scans in 1 of 2 ways:

- **An area**: the whole repo, a module or some files. It lists everything there: type errors, lint findings and every smell, with the hotspots and the check-up's counters.
- **A change**: the uncommitted work, what is staged, a commit or this branch. It lists what the change made worse and the old smells in the code it touched.

The report names the scope, groups the findings most severe first and names every tool that was missing. It ends with an offer to fix what the user picks, and waits for the answer.

`broom sweep` checks the same scopes from the command line, and formats them unless `--check` is given. A sweep of the whole repo only reports unless `--fix` is given.

1 gap:

- A scan from one commit covers every change since it, later commits included.

- **Commands**:
  - [broom sweep](../CLI.md#broom-sweep)
  - [broom diagnose](../CLI.md#broom-diagnose)
  - [broom fmt](../CLI.md#broom-fmt)
- **Why**: [035: Three commands, and a cleanup that is none](../specs/decisions/035-three-commands.md)

**Stories** (1):

- A user about to send a branch for review scans it to see what it made worse, and decides what to fix.

---

## F2.7: Time limit

One run of any hook takes at most 30 seconds. A tool that runs out of time is cut off with everything it started. The check goes ahead without it and says so in a note.

A commit or a stop that a tool kept from finishing is never blocked for it. A check that ran out of time is skipped until the repo's HEAD moves, in every session, with a note. A cold `cargo clippy` or `swift build` can time out.

A hook still running after 20 seconds writes `hook-trace.log` in broom's data directory.

- **Design**:
  - [3. A hook run ends within 30 seconds](../DESIGNS.md#3-a-hook-run-ends-within-30-seconds)
  - [5. A tool that is missing or fails never blocks](../DESIGNS.md#5-a-tool-that-is-missing-or-fails-never-blocks)
- **How it works**: [Hook limits](../specs/hook-limits.md)
- **Why**:
  - [024: Tools are kept to a quarter of the cores](../specs/decisions/024-thread-caps.md)
  - [025: A command writes to files](../specs/decisions/025-files-not-pipes.md)
  - [026: A hook run is cut at 30 seconds](../specs/decisions/026-thirty-second-hook.md)

---

## F2.8: Self-waivers shown

A change that loosens the bar is listed in the turn's summary and in the record. It is not blocked.

3 kinds:

- A change to `.broom.json` that turns a smell off, raises a limit, excludes a path or names a new test command.
- A new lint suppression, with a reason or without, in code or in a YAML, shell or HTML comment.
- A commit made with `--no-verify`.

A `.broom.json` loosened by a command, such as `sed`, is seen at the turn's end. With `check_on` at `commit` no turn's end looks, and such a change is missed when the content of every committed file had already passed.

- **Stance**: [Say what happened](../PHILOSOPHY.md#what-happens-to-what-was-skipped)
- **How it works**: [Record](../specs/record.md)

---

## F2.9: Messages that say how to fix

A block says first what was blocked and what to do, then lists the findings. After them it gives the usual fix of each kind of smell found, one line per kind, the same line `broom fixes` prints. A linter's or a type checker's finding gets no line, since its own message says it.

The message then says what is not a fix: a function cut in two at an arbitrary line, a new lint suppression and a looser `.broom.json`. The way to accept a finding comes last.

A message holds at most 9,000 characters. Past that it shows fewer findings and says how many more there are. A nit told at a commit ends with the fix of up to 3 of its kinds.

- **Commands**: [broom fixes](../CLI.md#broom-fixes)
- **How it works**: [Commit check](../specs/commit-check.md)

---

## F2.10: Check after an edit

After each edit broom formats the file and runs what can be judged in milliseconds. It tells Claude what it found on the lines that changed, each finding once, and never blocks. 3 linters run here: ruff · oxlint without its type-aware rules · SwiftLint.

What is told after an edit and still there at the commit is blocked there. `check_on` at `off` turns the check off, and `format_on` at `commit` or `off` turns the format off.

2 gaps:

- A project that lints with ESLint, biome or stylelint alone gets no check here, since those take too long for an edit.
- Go and Rust get none, since their linters need a build.

- **Stance**: [At three moments of Claude's flow](../PHILOSOPHY.md#when-may-a-check-interrupt)
- **How it works**: [Edit check](../specs/edit-check.md)
- **Why**: [032: After an edit broom formats and runs what is judged in milliseconds](../specs/decisions/032-light-check-after-an-edit.md)

---

## F2.11: Nothing is waved through

A finding that is more than slight passes only fixed, or accepted with a reason. Trying again passes nothing.

3 things follow:

- A hint blocks a commit, so no smell enters the repo for a later commit to clean.
- A turn's end blocks again until what is left is fixed or accepted, so Claude goes back and finishes before it replies.
- After three blocks broom lets go, and tells the user what is still open in words that can't be missed.

A nit, which is slight, is told and never blocks: magic numbers · TODO comments · dead code · a new file with no test · any smell a detector guesses.

- **Stance**: [Fixed, or let through with a reason the user sees](../PHILOSOPHY.md#how-does-a-finding-end)
- **Design**: [6. A finding ends fixed or with a reason the user sees](../DESIGNS.md#6-a-finding-ends-fixed-or-with-a-reason-the-user-sees)
- **Why**: [031: Trying again passes nothing, and three blocks end in a loud give-up](../specs/decisions/031-no-pass-on-a-second-try.md)

---

## F2.12: A pass is told to the user

A block tells Claude to accept only for a real reason, such as a refactor that comes in a later step, and to say in its reply what it accepted and why. The turn's summary names each accepted finding with its reason.

When the user must decide, Claude runs `broom known --ask "<question>"` and stops. That passes nothing: the commit is still denied and the finding stays open. The turn ends, and the user's line opens with `WAITS FOR YOUR ANSWER` and the question. A later turn's end blocks on the finding again only when that turn changed its file, and a commit of its file is denied until it is fixed or accepted.

When the user said yes, Claude accepts with `--agreed`, and the summary shows that finding as one the user agreed to. A turn in which Claude accepted 3 findings or more on its own opens the user's line with `Claude ACCEPTED`, so a reason never becomes the cheap way out.

An accepted finding stays on record: `broom known` lists it with its reason, and it is raised again once its code changes.

3 gaps:

- With `check_on` at `commit` no turn's end shows the line, so Claude's own reply has to carry the question.
- A subagent that asks about a denied commit is still blocked at its own end.
- A finding asked about leaves Claude's sight once the turns move to other files. [F2.14: Open findings come back](#f214-open-findings-come-back) tells it again.

- **Stance**: [Fixed, or let through with a reason the user sees](../PHILOSOPHY.md#how-does-a-finding-end)
- **Commands**: [broom known](../CLI.md#broom-known)
- **How it works**:
  - [Turn end](../specs/turn-end.md)
  - [Record](../specs/record.md)
- **Why**: [033: A turn can end with a question to the user, which passes nothing](../specs/decisions/033-ask-the-user.md)

---

## F2.13: A turn that changed code shows that tests ran

At a turn's end, a turn that changed code has work left over in 2 cases:

- A code file the turn changed holds content that no test run tested, and the block names up to three such files.
- The last test run failed, and the block names its exit code and its command.

It stops the turn's end like any finding, and passes when the tests ran and passed, by an accept with a reason or by a question to the user. An accept holds for that turn only. broom looks for the trace and runs no test itself. It judges by content and not by time, so code tested in a worktree and merged afterwards, in a later turn too, counts as tested. It knows a test run by the words of the command, from a list of runners and from what `.broom.json` names in `test_commands`.

It applies where the repo tracks a test file, and at the main session's end only. `smells_off: ["tests_not_run"]` turns it off.

3 gaps:

- A test run in the background, or piped into another command, counts as passed.
- A runner of a project's own goes unseen until `test_commands` names it. The block's fix line says so where the repo names none.
- A command that rewrites code and then runs the tests reads as a change after the run.

- **Stance**: [At three moments of Claude's flow](../PHILOSOPHY.md#when-may-a-check-interrupt)
- **How it works**: [Turn end](../specs/turn-end.md)
- **Why**: [034: A test run is known by the hook events of its command, and its accept holds for one turn](../specs/decisions/034-test-run-by-hook-events.md)

---

## F2.14: Open findings come back

A finding that stopped a commit or a turn's end and that no check has ended is told to Claude again, until it is fixed or accepted. No problem leaves Claude's sight because the turns moved to other files or a new session began.

It is told at 2 moments:

- **The next prompt after a question**: the user's answer has come, so Claude is told the findings it asked about, to fix them or to accept them with `--agreed`.
- **A session's start in the repo**: Claude is told the findings still open there, asked about or not.

Before it tells, broom checks the files of those findings again with the rules of the day. A finding no longer there is recorded as fixed and is not told, so a rule changed since or a fix made by hand makes no noise. At the prompt after a question that check would hold up the prompt, so Claude is told from the record at once, and the check runs right after: a finding it finds gone is recorded as fixed and told as gone on a later turn.

The message gives how many findings are open, names up to 5 and says how many more there are. Claude is told to fix them when it fits, and to tell the user at a natural point. The user sees nothing of it.

It tells and never blocks. The finding still blocks wherever a check covers its file, and a commit or a turn's end that covers its file and no longer finds it records it as fixed.

A prompt with no question waiting costs one shell start, about 10 ms, and no Python. A session's start with nothing open reads the ledger and runs no check.

4 gaps:

- A finding fixed by hand between the question and the answer is told once at the answer, and told as gone on the next turn.
- A finding blocked before 0.30.0 is matched by its file, tool and rule only, so one that shares them with another open finding of its file may still be told after its fix.
- With less than 6 seconds of a session start's hook left, the findings are told without the check again.
- With a cold tool cache, a check again of many files can run out of the hook's time and end none, until a later check.

- **Stance**: [Fixed, or let through with a reason the user sees](../PHILOSOPHY.md#how-does-a-finding-end)
- **Why**: [044: An open finding comes back until it ends](../specs/decisions/044-open-findings-come-back.md)
