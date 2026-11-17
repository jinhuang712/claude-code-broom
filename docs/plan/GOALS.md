# Goals

The goals are checked at the end of a checkpoint and before a release. The test suite is `python3 tests/run.py`.

---

## Summary

```
Goals
├── Objectives
│   ├── ✅ O1: Clean work without asking — Claude's changes meet the project's rules
│   ├── ⬜ O2: Tooling in one conversation — a bare repo ends with no gap
│   ├── ⬜ O3: Mistakes seen while editing — a diagnostic after an edit
│   ├── ✅ O4: Nothing passes silently — every pass has a reason the user can see
│   ├── ✅ O5: A full diagnosis of an old repo — every smell, with no time cut
│   ├── ✅ O6: A number that got worse is told once — the check-up speaks only then
│   └── ❌ O7: No script to write — broom answers what a session would count by hand
├── Measures
│   ├── ⬜ M1: Fix rate — how much of what broom blocks gets fixed
│   └── ⬜ M2: Check time — the seconds a commit check takes
├── Thresholds
│   ├── ✅ T1: An idle Bash call costs 15 ms at most
│   ├── ✅ T2: An idle Python hook costs 50 ms at most
│   ├── ✅ T3: A hook run takes 30 seconds at most
│   └── ✅ T4: Content that passed is let through in 100 ms at most
└── Constraints
    ├── ✅ R1: No old warning blocks Claude
    ├── ✅ R2: A false positive costs one round
    ├── ✅ R3: An old smell in untouched code never comes up
    └── ✅ R4: Setup asks at most two questions
```

---

## Goals

---

### Objectives

---

#### O1: Clean work without asking

Claude's work comes out formatted, lint-clean and type-correct by the project's own rules.

**Want**: clean work without asking.

**Checks**: [F2.1: Commit check](../features/F2-sweep.md#f21-commit-check) · [F2.2: Turn-end check](../features/F2-sweep.md#f22-turn-end-check)

**Acceptance**: The test suite passes. It commits and stops in temporary repos and expects the block.

**Status**: ✅ 2026-11-17, 501 tests with 3 skipped.

---

#### O2: Tooling in one conversation

A repo with no tooling gets working tooling in one short conversation.

**Want**: tooling in one conversation.

**Checks**: [F1.3: /broom:setup](../features/F1-setup.md#f13-broomsetup)

**Acceptance**: In a repo with no tools and no configs, one run of `/broom:setup` ends with `broom doctor` printing `All set.`.

**Status**: ⬜

---

#### O3: Mistakes seen while editing

Claude sees its mistakes as it edits, through language servers.

**Want**: mistakes seen while editing.

**Checks**: [F6.1: Diagnostics as Claude edits](../features/F6-language-servers.md#f61-diagnostics-as-claude-edits)

**Acceptance**: After an edit that adds a type error, Claude Code shows the server's diagnostic, in each of the six languages.

**Status**: ⬜

---

#### O4: Nothing passes silently

A finding is fixed, or it leaves a reason the user can see.

**Want**: nothing passes silently.

**Checks**: [F9.1: Ledger](../features/F9-record.md#f91-ledger) · [F9.2: Turn summary](../features/F9-record.md#f92-turn-summary) · [F2.5.1: A reason for every pass](../features/F2-sweep.md#f251-a-reason-for-every-pass)

**Acceptance**: A test lets a finding through by each way broom has. Each way leaves a ledger line with a reason, and the turn's summary names it.

**Status**: ✅ 2026-11-17, for the three ways: accepted with a reason and a turn ended with the finding open by `tests/test_ledger.py`, and a turn given up after three blocks by `tests/test_turncheck.py`.

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

**Checks**: [F10.4: Numbers on request](../features/F10-diagnosis.md#f104-numbers-on-request) · [F10.5: Claude knows what to ask](../features/F10-diagnosis.md#f105-claude-knows-what-to-ask)

**Acceptance**: A fresh session is asked ten questions about a repo: its size, its longest functions, its skipped tests, its untested files and each rot counter among them. It answers all ten with broom commands and writes no script.

**Status**: ❌ 2026-11-17, in three fresh sessions. On a real TS/JS repo with 0.22.0, nine answers came from broom, no script was written, and coverage had no report to read. On a throwaway repo of three languages, six answers came from broom alone with 0.22.2 and nine with 0.22.4. The tenth, the public code with no doc comment, was counted by hand in TS/JS, and one script read broom's own JSON for the dead code. [I12: A fresh session finishes one of ten answers by hand](ISSUES.md#i12-a-fresh-session-finishes-one-of-ten-answers-by-hand) holds the work.

---

### Measures

---

#### M1: Fix rate

How much of what broom blocks gets fixed. A low rate for one rule means the rule is noise.

**Want**: a ruler in everyday work.

**Checks**: [F9.3: Report](../features/F9-record.md#f93-report) · [F9.4: Tiers by fix rate](../features/F9-record.md#f94-tiers-by-fix-rate)

**How**: The ledger of the author's machine over 30 days.

**Formula**:

```
M1 = findings fixed after a block / findings blocked        per rule, and over all rules
```

**Last value**: open, since broom keeps no record of fixes yet.

---

#### M2: Check time

The seconds a commit check takes when it has to run.

**Want**: nothing to pay when idle.

**Checks**: [F2.7: Time limit](../features/F2-sweep.md#f27-time-limit)

**How**: The ledger of the author's machine over 30 days.

**Formula**:

```
M2 = median seconds of a commit check that ran at least one tool
```

**Last value**: open. Single runs recorded on 2026-11-16: 3.8 s for a second check of 30 Go files, and 9.7 s beside a busy job.

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

**Status**: ✅ 2026-11-17, on an Apple M5 Pro with Python 3.14: `broom hook edit` took 31 ms and `broom hook stop` 39 ms, each the median of 30 runs. `tests/test_turnhooks.py` and `tests/test_edithook.py` hold what the time rests on: one git call at most and no check loaded.

---

#### T3: A hook run takes 30 seconds at most

**Want**: nothing to pay when idle.

**Checks**: [3. A hook run ends within 30 seconds](../DESIGNS.md#3-a-hook-run-ends-within-30-seconds) · [F2.7: Time limit](../features/F2-sweep.md#f27-time-limit)

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

**Checks**: [6. A false positive costs one round](../DESIGNS.md#6-a-false-positive-costs-one-round)

**Condition**: A finding that is wrong passes with one command, and a turn's end never blocks twice without a new edit.

**How**: A test accepts a blocked finding with a reason and commits, and another stops twice and expects the turn to end.

**Status**: ✅ 2026-11-17, by `tests/test_commit.py`, where a blocked commit passes once accepted with a reason, and by `tests/test_turncheck.py`, where a second stop ends the turn.

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

**Checks**: [F1.3: /broom:setup](../features/F1-setup.md#f13-broomsetup)

**Condition**: Both questions come before broom acts on the user's machine or repo, and no setting is asked.

**How**: Read the skill and count the questions.

**Status**: ✅ 2026-11-17, by reading `skills/setup/SKILL.md`: two questions in one call before anything is run, and no setting among them. The offer to disable a conflicting plugin was a third question until that day, and is now one of the commands of the first.
