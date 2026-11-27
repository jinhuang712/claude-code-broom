# Roadmap

**Current checkpoint**: [CP8: Lighter](#cp8-lighter). [CP15: Sharper rules and more rot](#cp15-sharper-rules-and-more-rot) shipped its 13 items on 2026-11-27 and waits for the fix rate it is judged by. [CP14: No clock](#cp14-no-clock) and [CP13: Nothing is forgotten](#cp13-nothing-is-forgotten) ended that day, in that order at the user's word. [CP8: Lighter](#cp8-lighter) waits for the ledger's numbers from 0.29.0: 100 checks that ran a tool for the check time and 100 findings that ended for the fix rate. The user set on 2026-11-20 that no feature is added until then, and lifted that for CP13, CP14 and CP15. What follows them is open in [What it takes for a second user to install broom and stay](TODO.md#p1discussion-what-it-takes-for-a-second-user-to-install-broom-and-stay). [CP9: Ready for a public release](#cp9-ready-for-a-public-release) ended on 2026-11-20 with 0.28.0, once the README got its hero. CP10 ended on 2026-11-20 with 0.26.0, and [CP11: Read from a syntax tree](#cp11-read-from-a-syntax-tree) with 0.27.0 that day. CP6 ended on 2026-11-19 with 0.25.0, once the user moved its last two items to [CP9: Ready for a public release](#cp9-ready-for-a-public-release). CP2 and CP3 shipped, and their goals that need use are still open. CP7 ended with 0.24.0, CP5 with 0.22.0, CP2.2 with 0.22.2 and CP4 with 0.23.0.

---

## Summary

```
Roadmap
├── ✅ CP1: 0.18.1 reaches users — the hook limits and the docs set are released
├── 🟨 CP2: Nothing passes silently — every pass leaves a reason the user sees
│   ├── 🟨 CP2.1: The ledger
│   └── ✅ CP2.2: Reasons and self-waivers
├── 🟨 CP3: Claude knows how to fix — the bar before the work, the fix beside the finding
│   ├── 🟨 CP3.1: Messages that say how to fix
│   ├── 🟨 CP3.2: Limits told before the work
│   └── ✅ CP3.3: Old smells in touched code
├── ✅ CP4: A refactoring kit — a full diagnosis, the worst places first, the numbers after
├── ✅ CP5: A check-up for rot — numbers that speak when they grow
│   ├── ✅ CP5.1: Counters, dead code and comments
│   ├── ✅ CP5.2: Tests: coverage, duplicates and skips
│   ├── ✅ CP5.3: Dependencies and deprecated APIs
│   └── ✅ CP5.4: Rust's missing smells
├── ✅ CP6: Polish and self-test — every goal run in a real session, every rough edge smoothed
├── ✅ CP7: Nothing is waved through — three moments in Claude's flow, and no pass without a reason
├── ⬜ CP8: Lighter — less code, fewer runs, less noise
│   ├── ⬜ CP8.1: Fewer interruptions
│   └── ⬜ CP8.2: Fewer runs and less code
├── ✅ CP9: Ready for a public release — the README's face and the language servers proven
│   ├── ✅ CP9.1: Three commands
│   └── ✅ CP9.2: The README's face and the language servers
├── ✅ CP10: The same smells in every language — in the order the user set
│   ├── ✅ CP10.1: Python, TS/JS and Go
│   └── ✅ CP10.2: Swift and Rust
├── ✅ CP11: Read from a syntax tree — what no linter covers, read by a parser
├── ⬜ CP12: Waits for a need
├── ✅ CP13: Nothing is forgotten — an open finding comes back until it ends
├── ✅ CP14: No clock — events and counts, and what Claude hides still counts
└── 🟨 CP15: Sharper rules and more rot — shipped, the fix rate after it is open
```

---

## CP1: 0.18.1 reaches users

**Status**: ✅

Versions 0.18.0 and 0.18.1 and the docs set were pushed and tagged `v0.18.1` on 2026-11-17.

**Delivers** (2):

- [F2.7: Time limit](../features/F2-sweep.md#f27-time-limit)
- The docs in the what-we-build format, done on 2026-11-17.

**Exit criteria** (3):

- **Objectives**
  - [O1: Clean work without asking](GOALS.md#o1-clean-work-without-asking): ✅ 2026-11-16
- **Thresholds**
  - [T3: A hook run takes 30 seconds at most](GOALS.md#t3-a-hook-run-takes-30-seconds-at-most): ✅ 2026-11-16
- **Do not hold the release**
  - [T2: An idle Python hook costs 50 ms at most](GOALS.md#t2-an-idle-python-hook-costs-50-ms-at-most)

---

## CP2: Nothing passes silently

**Status**: 🟨

broom keeps no record of what it stopped and what was fixed, so nobody can say whether it works. This checkpoint gives it a record and makes every pass carry a reason.

**Exit criteria** (2):

- **Sub-checkpoints**
  - [CP2.1: The ledger](#cp21-the-ledger) is met.
  - [CP2.2: Reasons and self-waivers](#cp22-reasons-and-self-waivers) is met.

---

### CP2.1: The ledger

**Status**: 🟨

The three features shipped in 0.18.2 on 2026-11-17. The measures get their first value once the ledger holds 100 checks that ran a tool and 100 findings that ended, written by 0.29.0 or later: from that version every line holds broom's version, which `broom report --since` reads.

**Delivers** (5):

- [F9.1: Ledger](../features/F9-record.md#f91-ledger)
- [F9.2: Turn summary](../features/F9-record.md#f92-turn-summary)
- [F9.3: Report](../features/F9-record.md#f93-report)
- The report gives the seconds of a whole check, leaves out the throwaway repos in temporary folders and starts on a day with `--since`, done on 2026-11-20.
- A question to the user that nothing ended counts against its rule's fix rate and stays shown as open, done on 2026-11-26.

**Exit criteria** (2):

- **Measures**
  - [M1: Fix rate](GOALS.md#m1-fix-rate) has a first value.
  - [M2: Check time](GOALS.md#m2-check-time) has a first value.

---

### CP2.2: Reasons and self-waivers

**Status**: ✅

The three features shipped in 0.19.0 on 2026-11-17, and its two goals were matched to their tests that day.

**Delivers** (3):

- [F2.5.1: A reason for every pass](../features/F2-sweep.md#f251-a-reason-for-every-pass)
- [F2.8: Self-waivers shown](../features/F2-sweep.md#f28-self-waivers-shown)
- [F2.4.1: Offered at setup](../features/F2-sweep.md#f241-offered-at-setup)

**Exit criteria** (2):

- **Objectives**
  - [O4: Nothing passes silently](GOALS.md#o4-nothing-passes-silently): ✅ 2026-11-17
- **Constraints**
  - [R2: A false positive costs one round](GOALS.md#r2-a-false-positive-costs-one-round): ✅ 2026-11-17

---

## CP3: Claude knows how to fix

**Status**: 🟨

A block says what is over a limit and not what to do about it. This checkpoint puts the fix beside the finding and the bar before the work.

**Exit criteria** (3):

- **Sub-checkpoints**
  - [CP3.1: Messages that say how to fix](#cp31-messages-that-say-how-to-fix) is met.
  - [CP3.2: Limits told before the work](#cp32-limits-told-before-the-work) is met.
  - [CP3.3: Old smells in touched code](#cp33-old-smells-in-touched-code) is met.

---

### CP3.1: Messages that say how to fix

**Status**: 🟨

The feature shipped in 0.19.1 on 2026-11-17. The fix rate after it comes with use.

**Delivers** (1):

- [F2.9: Messages that say how to fix](../features/F2-sweep.md#f29-messages-that-say-how-to-fix)

**Exit criteria** (1):

- **Measures**
  - [M1: Fix rate](GOALS.md#m1-fix-rate) is recorded before and after.

---

### CP3.2: Limits told before the work

**Status**: 🟨

The feature shipped in 0.19.1 on 2026-11-17. The fix rate after it comes with use.

**Delivers** (1):

- [F4.8: Limits told before the work](../features/F4-smells.md#f48-limits-told-before-the-work)

**Exit criteria** (1):

- **Measures**
  - [M1: Fix rate](GOALS.md#m1-fix-rate) is recorded before and after.

---

### CP3.3: Old smells in touched code

**Status**: ✅

The feature shipped in 0.20.0 on 2026-11-17.

**Delivers** (1):

- [F4.9: Old smells in touched code](../features/F4-smells.md#f49-old-smells-in-touched-code)

**Exit criteria** (1):

- **Constraints**
  - [R3: An old smell in untouched code never comes up](GOALS.md#r3-an-old-smell-in-untouched-code-never-comes-up): ✅ 2026-11-17

---

## CP4: A refactoring kit

**Status**: ✅

Everything it delivers shipped by 0.21.0 on 2026-11-17, and a fresh session wrote no script with 0.22.7 that day. The checkpoint ended with 0.23.0.

A refactor starts from numbers: what is in the repo, where it hurts most and whether the work paid off.

**Delivers** (6):

- [F10.1: Whole-repo diagnosis](../features/F10-diagnosis.md#f101-whole-repo-diagnosis)
- [F10.2: Hotspots by churn](../features/F10-diagnosis.md#f102-hotspots-by-churn)
- [F10.3: Before and after](../features/F10-diagnosis.md#f103-before-and-after)
- [F10.4: Numbers on request](../features/F10-diagnosis.md#f104-numbers-on-request)
- [F10.5: Claude knows what to ask](../features/F10-diagnosis.md#f105-claude-knows-what-to-ask)
- A test run no longer writes into the user's data directory, done on 2026-11-17.

**Exit criteria** (2):

- **Objectives**
  - [O5: A full diagnosis of an old repo](GOALS.md#o5-a-full-diagnosis-of-an-old-repo): ✅ 2026-11-17
  - [O7: No script to write](GOALS.md#o7-no-script-to-write): ✅ 2026-11-17

---

## CP5: A check-up for rot

**Status**: ✅

Its four sub-checkpoints ended by 0.22.0 on 2026-11-17.

Rot is what gets worse with no one change at fault. The check-up counts it across the repo and speaks when a number grew.

**Exit criteria** (4):

- **Sub-checkpoints**
  - [CP5.1: Counters, dead code and comments](#cp51-counters-dead-code-and-comments) is met.
  - [CP5.2: Tests: coverage, duplicates and skips](#cp52-tests-coverage-duplicates-and-skips) is met.
  - [CP5.3: Dependencies and deprecated APIs](#cp53-dependencies-and-deprecated-apis) is met.
  - [CP5.4: Rust's missing smells](#cp54-rusts-missing-smells) is met.

---

### CP5.1: Counters, dead code and comments

**Status**: ✅

The four features shipped in 0.21.2 on 2026-11-17, with gaps: missing comments are not told in TS/JS, and a broad catch only in Python.

**Delivers** (4):

- [F11.1: Counters](../features/F11-checkup.md#f111-counters)
- [F11.4: Dead code in the whole repo](../features/F11-checkup.md#f114-dead-code-in-the-whole-repo)
- [F11.5: Missing comments](../features/F11-checkup.md#f115-missing-comments)
- [F4.2.1: Broad catch](../features/F4-smells.md#f421-broad-catch)

**Exit criteria** (1):

- **Objectives**
  - [O6: A number that got worse is told once](GOALS.md#o6-a-number-that-got-worse-is-told-once): ✅ 2026-11-17

---

### CP5.2: Tests: coverage, duplicates and skips

**Status**: ✅

The four features shipped in 0.22.0 on 2026-11-17, with gaps: coverage lists files and no functions, and a new file is paired with its test by name only.

**Delivers** (4):

- [F11.2: Test coverage](../features/F11-checkup.md#f112-test-coverage)
- [F11.3: Duplicate tests](../features/F11-checkup.md#f113-duplicate-tests)
- [F4.2.2: Skipped test](../features/F4-smells.md#f422-skipped-test)
- [F4.2.3: Untested file](../features/F4-smells.md#f423-untested-file)

**Exit criteria** (1):

- **Objectives**
  - [O6: A number that got worse is told once](GOALS.md#o6-a-number-that-got-worse-is-told-once): ✅ 2026-11-17, by `tests/test_testrot.py` and `tests/test_coverage.py`

---

### CP5.3: Dependencies and deprecated APIs

**Status**: ✅

The two features shipped in 0.22.0 on 2026-11-17, with gaps: Swift is left out of both, and Rust's tool for unused packages was never run here.

**Delivers** (2):

- [F11.6: Dependencies](../features/F11-checkup.md#f116-dependencies)
- [F11.7: Deprecated APIs](../features/F11-checkup.md#f117-deprecated-apis)

**Exit criteria** (1):

- **Objectives**
  - [O6: A number that got worse is told once](GOALS.md#o6-a-number-that-got-worse-is-told-once): ✅ 2026-11-17, by `tests/test_deprecated.py`

---

### CP5.4: Rust's missing smells

**Status**: ✅

The user lifted the hold on Rust's smells on 2026-11-17, and 7 more shipped in 0.21.1 that day.

**Delivers** (1):

- [F8.3: Rust](../features/F8-languages.md#f83-rust), with the smells it lacks.

**Exit criteria** (1):

- **Objectives**
  - [O1: Clean work without asking](GOALS.md#o1-clean-work-without-asking): ✅ 2026-11-17

---

## CP6: Polish and self-test

**Status**: ✅

It ended on 2026-11-19 with 0.25.0. That day the user moved the README's hero image and the language-server check to CP9, as work for just before a public release.

The user asked on 2026-11-17 for a round of polish and self-test once the features are in. broom is used end to end in fresh sessions, on throwaway repos and on real ones, and what that finds is fixed.

**Delivers** (11):

- [F1.5: Protection list](../features/F1-setup.md#f15-protection-list)
- A command added to `test_commands` is shown as a self-waiver, done on 2026-11-19.
- The plain doctor asks for the oxlint of the TS/JS smells whichever linter lints, and for each CSS project's formatter, done on 2026-11-19.
- Fresh sessions used broom end to end on a throwaway repo and on a public Python project, done on 2026-11-18.
  - They met 8 things: the limits card · the setup offer · a block with its fix lines · a fix · an accept with a reason · the turn's summary · the check-up's line · a checked commit.
- A turn-end block no longer takes a commit block's fix line with it, done on 2026-11-18.
- A blocked finding ends with one line in the record: none is lost at a commit of other files, done on 2026-11-18.
- git's own hook reads a linked worktree as it reads the main checkout, done on 2026-11-18.
- A fresh session answers ten questions about a repo from broom alone after five runs, done on 2026-11-17.
- README and INSTALL say which systems are supported, done on 2026-11-17.
- An idle turn's end starts git once where it started it 7 times, done on 2026-11-17.
  - An idle hook loads no check.
- A commit with a redirection or a heredoc message is checked where it passed unread before, done on 2026-11-17.

**Exit criteria** (5):

- **Objectives**
  - [O2: Tooling in one conversation](GOALS.md#o2-tooling-in-one-conversation): ✅ 2026-11-19, a bare Python repo set up in one run
  - [O7: No script to write](GOALS.md#o7-no-script-to-write): ✅ 2026-11-17, ten of ten answers from broom and no script
- **Thresholds**
  - [T2: An idle Python hook costs 50 ms at most](GOALS.md#t2-an-idle-python-hook-costs-50-ms-at-most): ✅ 2026-11-17, 31 ms for an edit and 39 ms for a turn's end
- **Constraints**
  - [R2: A false positive costs one round](GOALS.md#r2-a-false-positive-costs-one-round): ✅ 2026-11-17
  - [R4: Setup asks at most two questions](GOALS.md#r4-setup-asks-at-most-two-questions): ✅ 2026-11-17

---

## CP7: Nothing is waved through

**Status**: ✅

The four features shipped in 0.23.5 and 0.24.0 on 2026-11-18, and the checkpoint ended with 0.24.0.

The user set this on 2026-11-18: a check that lets Claude carry on puts Claude's speed before the code. Three moments get their own weight, and a finding ends fixed or with a reason the user sees.

**Delivers** (4):

- [F2.10: Check after an edit](../features/F2-sweep.md#f210-check-after-an-edit)
- [F2.11: Nothing is waved through](../features/F2-sweep.md#f211-nothing-is-waved-through)
- [F2.12: A pass is told to the user](../features/F2-sweep.md#f212-a-pass-is-told-to-the-user)
- [F2.13: A turn that changed code shows that tests ran](../features/F2-sweep.md#f213-a-turn-that-changed-code-shows-that-tests-ran)

**Exit criteria** (3):

- **Objectives**
  - [O8: Done means tests ran](GOALS.md#o8-done-means-tests-ran): ✅ 2026-11-18, in two fresh sessions
- **Thresholds**
  - [T5: A check after an edit costs 200 ms at most](GOALS.md#t5-a-check-after-an-edit-costs-200-ms-at-most): ✅ 2026-11-18, 146 to 160 ms in the worst case
- **Constraints**
  - [R5: Nothing is waved through](GOALS.md#r5-nothing-is-waved-through): ✅ 2026-11-18

---

## CP8: Lighter

**Status**: ⬜

The ledger's numbers say which rule is noise and which tool is slow. This checkpoint cuts by them.

**Exit criteria** (2):

- **Sub-checkpoints**
  - [CP8.1: Fewer interruptions](#cp81-fewer-interruptions) is met.
  - [CP8.2: Fewer runs and less code](#cp82-fewer-runs-and-less-code) is met.

---

### CP8.1: Fewer interruptions

**Status**: ⬜

**Delivers** (9):

- [F9.4: Tiers by fix rate](../features/F9-record.md#f94-tiers-by-fix-rate)
- A finding accepted in a linked worktree stays known once the work lands on the main checkout, done on 2026-11-20.
- A length counts code lines, so a comment line and a blank line stop no change, done on 2026-11-24.
- A test file may be twice as long as a code file, so a list of cases stops no change, done on 2026-11-24.
- A commit the turn brought in by a pull or a reset is not the turn's change, done on 2026-11-26.
- A wait for background work that never woke a turn ends at the next prompt after half an hour, done on 2026-11-26.
- Go's rules flag what their messages say, so a lookup table, a program's output, a checked type assertion and a setter stop no change, done on 2026-11-26.
- A Go test-helper package and `conftest.py` are test code, so a fixture's numbers stop no change, done on 2026-11-27.
- A known issue never expires, and a smell the user keeps is accepted by its place with their agreement, so `broom smells` can reach zero, done on 2026-11-27 at the user's request.

**Exit criteria** (1):

- **Measures**
  - [M1: Fix rate](GOALS.md#m1-fix-rate) is recorded before and after.

---

### CP8.2: Fewer runs and less code

**Status**: ⬜

**Delivers** (4):

- The test suite runs each file in a process of its own and takes about 40 seconds where it took 150, done on 2026-11-17.
- [I2: Three paths call the same tools](ISSUES.md#i2-three-paths-call-the-same-tools)
- [I5: Six rules sit on an alpha plugin API](ISSUES.md#i5-six-rules-sit-on-an-alpha-plugin-api)
- [I6: The Bash parser guesses what git's hook knows](ISSUES.md#i6-the-bash-parser-guesses-what-gits-hook-knows)

**Exit criteria** (2):

- **Measures**
  - [M2: Check time](GOALS.md#m2-check-time) is lower than at the end of CP2.1.
- **Thresholds**
  - [T2: An idle Python hook costs 50 ms at most](GOALS.md#t2-an-idle-python-hook-costs-50-ms-at-most)

---

## CP9: Ready for a public release

**Status**: ✅

The user set this on 2026-11-19: what a stranger meets first, and what can only be proven in real sessions of every language, comes just before a public release. The checkpoint ended with 0.28.0 on 2026-11-20.

**Exit criteria** (2):

- **Sub-checkpoints**
  - [CP9.1: Three commands](#cp91-three-commands) is met.
  - [CP9.2: The README's face and the language servers](#cp92-the-readmes-face-and-the-language-servers) is met.

---

### CP9.1: Three commands

**Status**: ✅

`/broom:status` shipped in 0.25.1 on 2026-11-19, and a fresh session with no tools on its PATH ran it end to end. The commands became three in 0.25.4 that day: setup, status and scan. Three fresh sessions ran a scan of a whole repo, a scan of two commits and a status, and none changed a file. One of them named the old cleanup command, which 0.25.5 put right.

**Delivers** (2):

- [F9.5: /broom:status](../features/F9-record.md#f95-broomstatus)
- [F2.6: Scan on request](../features/F2-sweep.md#f26-scan-on-request)

**Exit criteria** (1):

- **Constraints**
  - [R4: Setup asks at most two questions](GOALS.md#r4-setup-asks-at-most-two-questions): ✅ 2026-11-19, one question in the status skill

---

### CP9.2: The README's face and the language servers

**Status**: ✅

On 2026-11-20 a fresh session per language saw the server's diagnostic after an edit, in all six, so the hero image was what was left. The user picked its broom from options of Codex's that day, and the sub-checkpoint ended with 0.28.0.

**Delivers** (6):

- The README opens with a hero in a dark and a light version, and the changelog's sections before 0.18.2 meet the wording rules, done on 2026-11-20.
- A project on TypeScript 7 gets its folder cycles read, by a dependency-cruiser of broom's own, and the doctor no longer calls one that reads nothing ok, done on 2026-11-19.
- The line for another tool's git hook no longer blocks every commit where the marketplace copy is absent, and doctor sees it once added, done on 2026-11-19.
- The TypeScript language server starts in a project on TypeScript 7, from broom's own copy, done on 2026-11-19.
- An old cycle import that a change only moved no longer blocks the commit, done on 2026-11-19.
- Every enabled plugin whose language server competes with broom's is named in every repo, by the files it claims, done on 2026-11-19.

**Exit criteria** (1):

- **Objectives**
  - [O3: Mistakes seen while editing](GOALS.md#o3-mistakes-seen-while-editing): ✅ 2026-11-20, six languages in fresh sessions

---

## CP10: The same smells in every language

**Status**: ✅

The user set the order on 2026-11-19. Python and TS/JS come first, as the languages agents write most. Go comes with them, as the language backend work can't avoid. Swift and Rust come after.

**Exit criteria** (2):

- **Sub-checkpoints**
  - [CP10.1: Python, TS/JS and Go](#cp101-python-tsjs-and-go) is met.
  - [CP10.2: Swift and Rust](#cp102-swift-and-rust) is met.

---

### CP10.1: Python, TS/JS and Go

**Status**: ✅

TS/JS lacked 1 smell and Go lacked 3 that the language allows. All 4 shipped in 0.25.3 on 2026-11-19.

**Delivers** (3):

- [F4.2.1: Broad catch](../features/F4-smells.md#f421-broad-catch), in TS/JS and Go.
- [F4.1: Sized smells](../features/F4-smells.md#f41-sized-smells), with the length of a Go type.
- [F4.2: Occurrence smells](../features/F4-smells.md#f42-occurrence-smells), with a broad test assertion in Go.

**Exit criteria** (1):

- **Objectives**
  - [O9: The first three languages measure every smell](GOALS.md#o9-the-first-three-languages-measure-every-smell): ✅ 2026-11-19, 78 samples found

---

### CP10.2: Swift and Rust

**Status**: ✅

Swift gained 6 smells and Rust 10 in 0.25.11 on 2026-11-20, so Swift measures 25 and Rust 26. The user settled two questions that day: Swift rules out both cycles, and a nested `if` expression in Rust is a nested ternary. Rust's was read from its syntax tree in 0.26.0, where an `else if` chain stays flat, and the checkpoint ended that day.

**Delivers** (2):

- [F8.6: Swift](../features/F8-languages.md#f86-swift), with the smells it lacks.
- [F8.3: Rust](../features/F8-languages.md#f83-rust), with the smells it lacks.

**Exit criteria** (1):

- **Objectives**
  - [O10: Swift and Rust measure every smell](GOALS.md#o10-swift-and-rust-measure-every-smell): ✅ 2026-11-20, 25 samples in Swift and 27 in Rust

---

## CP11: Read from a syntax tree

**Status**: ✅

The user set this on 2026-11-20: a check rests on a mechanism and not on a text pattern, so it holds up as code varies. It moves every smell broom reads from text to a parser. The smells moved in 0.26.0 on 2026-11-20, the checks around them in 0.27.0 that day, and the checkpoint ended with it.

**Delivers** (6):

- `broom doctor` offers ast-grep for Go, Rust and TS/JS, and a check without it says so in a note, done on 2026-11-20.
- Swift's 9 text-read smells are read from its compiler's tree and SourceKit, done on 2026-11-20.
- Rust's 6 text-read smells and its `use` graph are read with ast-grep, done on 2026-11-20.
- Go's 3 text-read smells are read with ast-grep, done on 2026-11-20.
- Skipped tests, test cases and the comment counters are read from trees in every language, done on 2026-11-20.
- Suppressions, import growth, import lines, generated files and test callbacks are read from trees, and every language says where its grammar can't parse, done on 2026-11-20.

**Exit criteria** (3):

- **Objectives**
  - [O9: The first three languages measure every smell](GOALS.md#o9-the-first-three-languages-measure-every-smell): ✅ 2026-11-20, 27 in Python, 27 in TS/JS and 24 in Go
  - [O10: Swift and Rust measure every smell](GOALS.md#o10-swift-and-rust-measure-every-smell): ✅ 2026-11-20
- **Constraints**
  - [R6: No check reads code by a text pattern](GOALS.md#r6-no-check-reads-code-by-a-text-pattern): ✅ 2026-11-20, 65 regular expressions, none on source code

---

## CP12: Waits for a need

**Status**: ⬜

**Delivers** (1):

- [I3: The cause of the reported Stop hang is unconfirmed](ISSUES.md#i3-the-cause-of-the-reported-stop-hang-is-unconfirmed)

---

## CP13: Nothing is forgotten

**Status**: ✅

The user set this on 2026-11-26: the core want is that no problem is hidden, and that Claude is reminded of one until it is dealt with. A finding put to the user, or left in another session, left Claude's sight. It started once [CP14: No clock](#cp14-no-clock) had shipped, and ended on 2026-11-27 with 0.30.0. It didn't wait for CP8's numbers, which `broom report --since` splits at that version.

**Delivers** (1):

- [F2.14: Open findings come back](../features/F2-sweep.md#f214-open-findings-come-back)

**Exit criteria** (1):

- **Objectives**
  - [O11: No open finding is forgotten](GOALS.md#o11-no-open-finding-is-forgotten): ✅ 2026-11-27

---

## CP14: No clock

**Status**: ✅

The user set this on 2026-11-27: no rule of broom turns on the clock, and whatever Claude hides is only collapsed and still counts. Only broom's own running time keeps a bound. It ended that day, and ships in 0.29.0.

**Delivers** (9):

- A known issue never expires, done on 2026-11-27.
- A check that ran out of time is skipped until the repo's HEAD moves, done on 2026-11-27.
- Background work is waited for once per task, and a prompt during a wait keeps the waiting turn's changes, done on 2026-11-27.
- Content that passed and what the measurers found are kept by content and broom's version, bounded by count, done on 2026-11-27.
- Hotspots and history count the last 500 commits, with `--commits N`, done on 2026-11-27.
- The check-up counts TODO comments with no age, and a coverage report is behind when a code file it covers was written after it, done on 2026-11-27.
- `broom report` reads the whole record or from a version of broom, and every ledger line holds the version, done on 2026-11-27.
- The ledger, the session folders, the claims and the tools' caches are trimmed by size or count, done on 2026-11-27.
- What Claude hides is collapsed: every total counts it, and a line says how many, done on 2026-11-27.

**Exit criteria** (2):

- **Constraints**
  - [R7: No rule turns on the clock](GOALS.md#r7-no-rule-turns-on-the-clock): ✅ 2026-11-27
  - [R8: What is hidden still counts](GOALS.md#r8-what-is-hidden-still-counts): ✅ 2026-11-27

---

## CP15: Sharper rules and more rot

**Status**: 🟨

The user picked this on 2026-11-27 among the directions of TODO: rules that find fewer false smells, by the ledger's numbers and by real repos, and more kinds of rot found, none of them by the clock. It followed CP13. Its 13 items shipped on 2026-11-27 with 0.30.1, and the fix rate after them comes with use.

**Delivers** (13):

- A setter's boolean is no flag in Python, Rust, TS/JS and Swift, as in Go, done on 2026-11-27.
- Jest's and Vitest's helpers, `__mocks__/` and the setup files, are test code, done on 2026-11-27.
- A Go function that assigns another package's variable counts for `globals`, done on 2026-11-27.
- An edited file git ignores is left out of the turn's end, done on 2026-11-27.
- `broom known` marks an entry whose code changed, done on 2026-11-27.
- A Swift and a Rust function carry the lines they take, so a change near a long function's end is told, done on 2026-11-27.
- A repeated block counts code lines, done on 2026-11-27.
- A Go error dropped with `_` is a `swallowed_error` nit, done on 2026-11-27 and taken back out in 0.30.2.
- Unsafe code is a counter, done on 2026-11-27.
- Type escapes are a counter, done on 2026-11-27.
- Broken Markdown links are a counter, done on 2026-11-27.
- Lint suppressions in YAML, shell and HTML comments count, done on 2026-11-27.
- `broom stats` lists the largest tracked files, done on 2026-11-27.

**Exit criteria** (1):

- **Measures**
  - [M1: Fix rate](GOALS.md#m1-fix-rate) is recorded before and after.
