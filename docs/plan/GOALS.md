# Goals

The goals are checked at the end of a checkpoint and before a release. The test suite is `python3 tests/run.py`.

---

## Summary

```
Goals
├── Objectives
│   ├── ✅ O1: Clean work without asking — Claude's changes meet the project's rules
│   ├── ✅ O2: Tooling in one conversation — a bare repo ends with no gap
│   ├── ✅ O3: Mistakes seen while editing — a diagnostic after an edit
│   ├── ✅ O4: Nothing passes silently — every pass has a reason the user can see
│   ├── ✅ O5: A full diagnosis of an old repo — every smell, with no time cut
│   ├── ✅ O6: A number that got worse is told once — the check-up speaks only then
│   ├── ✅ O7: No script to write — broom answers what a session would count by hand
│   ├── ✅ O8: Done means tests ran — a turn that changed code ends with its tests run
│   ├── ✅ O9: The first three languages measure every smell — Python, TS/JS and Go
│   ├── ✅ O10: Swift and Rust measure every smell — bar what each language rules out
│   └── ✅ O11: No open finding is forgotten — Claude is told it again until it ends
├── Measures
│   ├── ⬜ M1: Fix rate — how much of what broom blocks gets fixed
│   └── ⬜ M2: Check time — the seconds a commit check takes
├── Thresholds
│   ├── ✅ T1: An idle Bash call costs 15 ms at most
│   ├── ✅ T2: An idle Python hook costs 50 ms at most
│   ├── ✅ T3: A hook run takes 30 seconds at most
│   ├── ✅ T4: Content that passed is let through in 100 ms at most
│   └── ✅ T5: A check after an edit costs 200 ms at most
└── Constraints
    ├── ✅ R1: No old warning blocks Claude
    ├── ✅ R2: A false positive costs one round
    ├── ✅ R3: An old smell in untouched code never comes up
    ├── ✅ R4: Setup asks at most two questions
    ├── ✅ R5: Nothing is waved through
    ├── ✅ R6: No check reads code by a text pattern
    ├── ✅ R7: No rule turns on the clock
    ├── ✅ R8: What is hidden still counts
    ├── ✅ R9: A test's shape never stops Claude
    └── ✅ R10: A repo's findings live in the repo
```

---

## Goals

---

### Objectives

---

#### O1: Clean work without asking

Claude's work comes out formatted, lint-clean and type-correct by the project's own rules.

**Want**: clean work without asking.

**Checks**:

- [F2.1: Commit check](../features/F2-sweep.md#f21-commit-check)
- [F2.2: Turn-end check](../features/F2-sweep.md#f22-turn-end-check)

**Acceptance**: The test suite passes. It commits and stops in temporary repos and expects the block.

**Status**: ✅ 2026-11-20, 770 tests with 3 skipped.

---

#### O2: Tooling in one conversation

A repo with no tooling gets working tooling in one short conversation.

**Want**: tooling in one conversation.

**Checks**: [F1.3: /broom:setup](../features/F1-setup.md#f13-broomsetup)

**Acceptance**: In a repo with no tools and no configs, one run of `/broom:setup` ends with `broom doctor` printing `All set.`.

**Status**: ✅ 2026-11-19, with 0.24.2. A fresh session ran `/broom:setup` once in a Python repo with no config, no git hook and none of its tools on the PATH. It installed ruff, pyright and jscpd, added the git hook and a ruff config, and `broom doctor` ended with `All set.`, in 12 turns. The PATH held only Python, git, Node and uv, and the installs went to a temporary folder, so the machine's own tools were never touched.

---

#### O3: Mistakes seen while editing

Claude sees its mistakes as it edits, through language servers.

**Want**: mistakes seen while editing.

**Checks**: [F6.1: Diagnostics as Claude edits](../features/F6-language-servers.md#f61-diagnostics-as-claude-edits)

**Acceptance**: After an edit that adds a type error, Claude Code shows the server's diagnostic, in each of the six languages.

**Status**: ✅ 2026-11-20, with 0.25.9 in Claude Code 2.1.329. One fresh `claude -p` session per language edited a small throwaway project to add a type error, an unknown property for CSS. Each transcript holds the diagnostic Claude Code gave the model after the edit: gopls, typescript-language-server through broom's launcher, rust-analyzer, pyright, sourcekit-lsp and vscode-css-language-server. Each needed one try. The debug log of the CSS run shows that Claude Code loaded broom's six servers and started its CSS one, and no other plugin served these files.

---

#### O4: Nothing passes silently

A finding is fixed, or it leaves a reason the user can see.

**Want**: nothing passes silently.

**Checks**:

- [F9.1: Ledger](../features/F9-record.md#f91-ledger)
- [F9.2: Turn summary](../features/F9-record.md#f92-turn-summary)
- [F2.5.1: A reason for every pass](../features/F2-sweep.md#f251-a-reason-for-every-pass)

**Acceptance**: A test lets a finding through by each way broom has. Each way leaves a ledger line with a reason, and the turn's summary names it.

**Status**: ✅ 2026-11-19, for the two ways left since a second stop stopped passing: accepted with a reason, and given up after three blocks. `tests/test_ledger.py` checks both pass lines and the turn's summary of each, and `tests/test_asked.py` checks an accept the user agreed to. A question put with `--ask` is no way through, and it leaves an `ask` line.

---

#### O5: A full diagnosis of an old repo

One command measures a whole repo with no time cut.

**Want**: a tool for refactoring.

**Checks**: [F10.1: Whole-repo diagnosis](../features/F10-diagnosis.md#f101-whole-repo-diagnosis)

**Acceptance**: On a repo of more than 5,000 code files, the diagnosis ends without a `timeout:` note and names every missing tool.

**Status**: ✅ 2026-11-17, by `tests/test_diagnose.py` on 5,100 files and by runs on two open-source repos of 5,825 and 18,496 files.

---

#### O6: A number that got worse is told once

The check-up speaks when a counter grew, and stays quiet otherwise.

**Want**: clean as you go.

**Checks**: [F11.1: Counters](../features/F11-checkup.md#f111-counters)

**Acceptance**: A test adds a skipped test to a repo. The next session start tells Claude once, and the one after says nothing.

**Status**: ✅ 2026-11-17, by `tests/test_checkup.py`.

---

#### O7: No script to write

A session with broom installed gets a repo's numbers from broom.

**Want**: no script to write.

**Checks**:

- [F10.4: Numbers on request](../features/F10-diagnosis.md#f104-numbers-on-request)
- [F10.5: Claude knows what to ask](../features/F10-diagnosis.md#f105-claude-knows-what-to-ask)

**Acceptance**: A fresh session is asked ten questions about a repo: its size, its longest functions, its skipped tests, its untested files and each rot counter among them. It answers all ten with broom commands and writes no script.

**Status**: ✅ 2026-11-17, in the fifth fresh session on a throwaway repo of three languages, with 0.22.7: the numbers of all ten answers came from `broom stats`, `broom smells` and `broom diagnose`, and no script was written. The session checked samples of them with grep, `git log` and `git blame`, and they agreed. Four earlier sessions that day finished one to four answers by hand, and each gap was closed. On a real TS/JS repo with 0.22.0, nine answers came from broom and coverage had no report to read.

---

#### O8: Done means tests ran

A turn that changed code doesn't end before the project's tests ran on that code.

**Want**: clean work without asking.

**Checks**: [F2.13: A turn that changed code shows that tests ran](../features/F2-sweep.md#f213-a-turn-that-changed-code-shows-that-tests-ran)

**Acceptance**: A fresh session is asked for a change to code and told that it need not write tests. Its turn ends only after it ran the repo's tests on the changed code, or after it accepted the finding with a reason or asked the user.

**Status**: ✅ 2026-11-18, in two fresh sessions on a throwaway repo with 0.23.5 and this rule. The first ran the repo's tests on its own after the change, and its turn ended with no block. The second was told to run no test: its turn's end was blocked with `tests_not_run`, and it ended the turn with `broom known --ask`, which put the question to the user.

---

#### O9: The first three languages measure every smell

Python, TS/JS and Go each measure every smell of the bar, bar what the language rules out.

**Want**: a ruler in everyday work.

**Checks**:

- [F4: Smells](../features/F4-smells.md)
- [F8: Languages](../features/F8-languages.md)

**Acceptance**: A test adds each of the 27 smells in Python, in TS/JS and in Go, and expects broom to find it. Go is let off 3: a nested ternary and both cycles. A smell with no sample fails the test.

**Status**: ✅ 2026-11-20, by `tests/test_language_matrix_python.py`, `tests/test_language_matrix_ts.py` and `tests/test_language_matrix_go.py`, after the smells moved to syntax trees in 0.26.0: 27 samples in Python, 27 in TS/JS and 24 in Go were found. The folder cycle of TS/JS ran with broom's own dependency-cruiser.

---

#### O10: Swift and Rust measure every smell

Swift and Rust each measure every smell of the bar, bar what the language rules out.

**Want**: a ruler in everyday work.

**Checks**:

- [F8.3: Rust](../features/F8-languages.md#f83-rust)
- [F8.6: Swift](../features/F8-languages.md#f86-swift)

**Acceptance**: The test of [O9: The first three languages measure every smell](#o9-the-first-three-languages-measure-every-smell) holds Swift and Rust too, each with a named list of what the language rules out.

**Status**: ✅ 2026-11-20, by `tests/test_language_matrix_swift.py` and `tests/test_language_matrix_rust.py`: 25 samples in Swift and 27 in Rust were found, each read from a syntax tree. Swift is let off both cycles, since a Swift file imports modules and never another file, and SwiftPM refuses modules that depend on one another. Rust is let off none.

---

#### O11: No open finding is forgotten

A finding that no check has ended is told to Claude again until it is fixed or accepted.

**Want**: nothing passes silently.

**Checks**: [F2.14: Open findings come back](../features/F2-sweep.md#f214-open-findings-come-back)

**Acceptance**: A test blocks two findings and puts them to the user. A next prompt and a new session in the repo touch no file, and Claude is told both at each. One of them fixed by hand in between is not told at the new session, and the record holds it as fixed.

**Status**: ✅ 2026-11-27, by `tests/test_comeback.py`: two findings blocked and put to the user are told at the next prompt and at a new session, which touch no file, and one fixed by hand in between is not told at the new session and holds a fix line. An idle prompt starts no Python, and an idle session start runs no check.

---

### Measures

---

#### M1: Fix rate

How much of what broom blocks gets fixed. A low rate for one rule means the rule is noise.

**Want**: a ruler in everyday work.

**Checks**:

- [F9.3: Report](../features/F9-record.md#f93-report)
- [F9.4: Tiers by fix rate](../features/F9-record.md#f94-tiers-by-fix-rate)

**How**: The ledger of the author's machine, read as the fix rate of `broom report --all --since 0.29.0`, once 100 findings have ended. A finding still open after a question to the user counts against its rule, and any other open finding counts against none. The report leaves out the throwaway repos in temporary folders. `--since` splits a rule's numbers at the version the rule changed in.

**Formula**:

```
M1 = fixed / (fixed + let through + open after a question)        per rule, and over all rules
```

**Last value**: open. Until 0.28.3 on 2026-11-26 a turn that pulled commits was blocked for every finding in them, and the ledger holds one such turn, so the first value was to count from 0.28.3. Lines hold broom's version only from 0.29.0, so `--since` can't tell 0.28.3's lines apart, and the first value counts from 0.29.0.

---

#### M2: Check time

The seconds a commit check takes when it has to run.

**Want**: nothing to pay when idle.

**Checks**: [F2.7: Time limit](../features/F2-sweep.md#f27-time-limit)

**How**: The ledger of the author's machine, read from the `at a commit` line of `broom report --all --since 0.29.0`, once 100 checks have run a tool.

**Formula**:

```
M2 = median seconds of a commit check that ran at least one tool
```

**Last value**: open, since the ledger began to hold a whole check's seconds on 2026-11-20. Single runs recorded on 2026-11-16: 3.8 s for a second check of 30 Go files, and 9.7 s beside a busy job.

---

### Thresholds

---

#### T1: An idle Bash call costs 15 ms at most

A Bash call that isn't a commit must not be felt.

**Want**: nothing to pay when idle.

**Checks**: [2. An idle hook exits in milliseconds](../DESIGNS.md#2-an-idle-hook-exits-in-milliseconds)

**Limit**: 15 ms.

**How**: Time `hooks/commit.sh` on a command with no `git commit`.

**Status**: ✅ 2026-09-23, about 13 ms.

---

#### T2: An idle Python hook costs 50 ms at most

An edit or a turn's end with nothing to check costs one Python start.

**Want**: nothing to pay when idle.

**Checks**: [2. An idle hook exits in milliseconds](../DESIGNS.md#2-an-idle-hook-exits-in-milliseconds)

**Limit**: 50 ms.

**How**: Time `broom hook edit` and `broom hook stop` with nothing to do.

**Status**: ✅ 2026-11-17, on an Apple M5 Pro with Python 3.14: `broom hook edit` took 31 ms and `broom hook stop` 39 ms, each the median of 30 runs. Later that day, with a bare `python3` start at 16 ms where it had been 14.5, they took 32 ms and 46 ms. `tests/test_turnhooks.py` and `tests/test_edithook.py` hold what the time rests on: one git call at most and no check loaded.

---

#### T3: A hook run takes 30 seconds at most

**Want**: nothing to pay when idle.

**Checks**:

- [3. A hook run ends within 30 seconds](../DESIGNS.md#3-a-hook-run-ends-within-30-seconds)
- [F2.7: Time limit](../features/F2-sweep.md#f27-time-limit)

**Limit**: 30 seconds.

**How**: `tests/test_hook_time.py` runs hooks against tools that never finish.

**Status**: ✅ 2026-11-16

---

#### T4: Content that passed is let through in 100 ms at most

**Want**: nothing to pay when idle.

**Checks**: [F2.1: Commit check](../features/F2-sweep.md#f21-commit-check)

**Limit**: 100 ms.

**How**: Commit the same content twice and time the second check.

**Status**: ✅ 2026-11-15, about 30 ms on a 29-file commit.

---

#### T5: A check after an edit costs 200 ms at most

An edit must not be felt, since Claude makes many in a row.

**Want**: clean work without asking.

**Checks**: [F2.10: Check after an edit](../features/F2-sweep.md#f210-check-after-an-edit)

**Limit**: 200 ms, set on 2026-11-18 from a Python start of about 30 ms and a lint of one file by ruff in about 10 ms.

**How**: Time `broom hook edit` on an edit of one Python file with ruff installed.

**Status**: ✅ 2026-11-18, on an Apple M5 Pro with Python 3.14 and other sessions running: the worst case took 146 to 160 ms, the median of 30 runs in each of four batches. The worst case is a formatter that rewrites the file, one new finding and a new session. An edit of a file with nothing to check took about 40 ms.

---

### Constraints

---

#### R1: No old warning blocks Claude

**Want**: clean work without asking.

**Checks**: [4. A finding counts only where the change made things worse](../DESIGNS.md#4-a-finding-counts-only-where-the-change-made-things-worse)

**Condition**: A finding on a line the change didn't touch never blocks, unless it is a type error.

**How**: `tests/test_commit.py` commits beside an old finding on an untouched line.

**Status**: ✅ 2026-11-16

---

#### R2: A false positive costs one round

**Want**: clean work without asking.

**Checks**: [6. A finding ends fixed or with a reason the user sees](../DESIGNS.md#6-a-finding-ends-fixed-or-with-a-reason-the-user-sees)

**Condition**: A finding that is wrong passes with one command and a reason.

**How**: A test accepts a blocked finding with a reason and commits.

**Status**: ✅ 2026-11-17, by `tests/test_commit.py`, where a blocked commit passes once accepted with a reason. Until 2026-11-18 the condition also held that a turn's end never blocks twice without a new edit. The user took that clause out, and [R5: Nothing is waved through](#r5-nothing-is-waved-through) holds the opposite.

---

#### R3: An old smell in untouched code never comes up

**Want**: a ruler in everyday work.

**Checks**: [F4.1: Sized smells](../features/F4-smells.md#f41-sized-smells)

**Condition**: A change gets no hint and no block for an old smell in a function or a file it didn't touch.

**How**: `tests/test_touched.py` edits one function of a file and leaves alone another function that is past the soft limit.

**Status**: ✅ 2026-11-17

---

#### R4: Setup asks at most two questions

**Want**: tooling in one conversation.

**Checks**:

- [F1.3: /broom:setup](../features/F1-setup.md#f13-broomsetup)
- [F9.5: /broom:status](../features/F9-record.md#f95-broomstatus)

**Condition**: Both questions come before broom acts on the user's machine or repo, and no setting is asked.

**How**: Read the skill and count the questions.

**Status**: ✅ 2026-11-17, by reading `skills/setup/SKILL.md`: two questions in one call before anything is run, and no setting among them. The offer to disable a conflicting plugin was a third question until that day, and is now one of the commands of the first. On 2026-11-19 `skills/status/SKILL.md` was read the same way: one question, and no setting.

---

#### R5: Nothing is waved through

**Want**: nothing passes silently.

**Checks**:

- [6. A finding ends fixed or with a reason the user sees](../DESIGNS.md#6-a-finding-ends-fixed-or-with-a-reason-the-user-sees)
- [F2.11: Nothing is waved through](../features/F2-sweep.md#f211-nothing-is-waved-through)

**Condition**: A finding that is more than slight passes a commit or a turn's end only fixed or accepted with a reason. Trying again passes nothing, until broom lets go after three blocks and tells the user what is still open.

**How**: A test commits a change with a hint and expects the block, and another stops twice and expects the second block.

**Status**: ✅ 2026-11-18, by `tests/test_nowave.py`: a commit with a hint is denied, a turn's end blocks three times without an edit, and the fourth stop gives up with the loud line.

---

#### R6: No check reads code by a text pattern

**Want**: a ruler in everyday work.

**Checks**:

- [9. A smell is read from a syntax tree, never from a text pattern](../DESIGNS.md#9-a-smell-is-read-from-a-syntax-tree-never-from-a-text-pattern)
- [F4: Smells](../features/F4-smells.md)

**Condition**: Every regular expression in `lib/broom` reads a tool's output, a path, a command or the text of one token a syntax tree isolated, and none reads source code.

**How**: A test lists each regular expression in `lib/broom` with what it reads, and fails on one the list doesn't hold.

**Status**: ✅ 2026-11-20, by `tests/test_no_text_patterns.py`: 65 regular expressions, each listed with what it reads. 40 read a tool's output, 7 a command, 7 a path, 4 a row's identity key, 4 one token a tree isolated and 3 a setting.

---

#### R7: No rule turns on the clock

**Want**: nothing passes silently.

**Checks**: [10. No rule turns on the clock](../DESIGNS.md#10-no-rule-turns-on-the-clock)

**Condition**: Nothing broom holds back or trims turns on how much time passed. Only broom's own running time has a bound, a record carries a stamp, and two events can be ordered.

**How**: `tests/test_no_clock.py` lists each reading of the clock in `lib/broom` with what it is for, and fails on one the list doesn't hold.

**Status**: ✅ 2026-11-27, by `tests/test_no_clock.py`: 36 readings, each listed. 14 bound broom's running time, 9 stamp a record, 11 order two events and 2 tell that a file changed.

---

#### R8: What is hidden still counts

**Want**: nothing passes silently.

**Checks**: [11. What is hidden still counts](../DESIGNS.md#11-what-is-hidden-still-counts)

**Condition**: A finding Claude accepted, or a note it quieted, leaves the lists and stays in every total, with a line that says how many are collapsed.

**How**: `tests/test_standing.py` accepts smells and issues and reads the totals of `broom smells`, `broom diagnose`, `broom sweep`, the session note, the commit check and the turn's end.

**Status**: ✅ 2026-11-27, by `tests/test_standing.py`.

---

#### R9: A test's shape never stops Claude

**Want**: clean work without asking.

**Checks**: [F4.7: Tests](../features/F4-smells.md#f47-tests)

**Condition**: In a test file only a skipped test, a broad test assertion, a swallowed error and a suppression stop a commit or a turn's end. Every other smell there is a nit, past the hard limit too.

**How**: A test commits a test file with a function past the hard limit, too many parameters and a skipped test, and expects the commit to stop on the skip alone, with the rest told as nits.

**Status**: ✅ 2026-11-27, by `tests/test_test_lies.py`: a 120-line function and a function of 9 parameters in a test file come back as nits, the commit stops on the skipped test alone, and it passes once the skip is gone.

---

#### R10: A repo's findings live in the repo

**Want**: nothing passes silently.

**Checks**: [F9.1: Ledger](../features/F9-record.md#f91-ledger)

**Condition**: A repo's known issues, its ledger, its last blocked result and its check-up live in its main checkout's `.broom/`, which git never tracks. A repo moved to another folder keeps them, and a `.broom/` that git tracks is never read.

**How**: A test accepts a finding, moves the repo to another folder and expects the finding still known and the report's numbers the same. Another commits a `.broom/` with a known issue and expects it never read, with a note.

**Status**: ✅ 2026-11-27, by `tests/test_repodata.py`: a repo moved to another folder keeps its known issue, its report's numbers and the commit it blocked, which `broom known --accept` still finds. A `.broom/` that git tracks is never read, by the hooks or by `broom report --all`, and the note says so. A copy of this machine's data moved this repo's 436 ledger lines and 4 known issues into its `.broom/` in 0.16 seconds, and the report gave the same numbers before and after.
