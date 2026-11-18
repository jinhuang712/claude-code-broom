# Roadmap

**Current checkpoint**: [CP7: Nothing is waved through](#cp7-nothing-is-waved-through), which the user put first on 2026-11-18, with [CP6: Polish and self-test](#cp6-polish-and-self-test) still open beside it. CP2 and CP3 shipped, and their goals that need use are still open. CP5 ended with 0.22.0, CP2.2 with 0.22.2 and CP4 with 0.23.0.

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
├── 🟨 CP6: Polish and self-test — every goal run in a real session, every rough edge smoothed
├── ⬜ CP7: Nothing is waved through — three moments in Claude's flow, and no pass without a reason
├── ⬜ CP8: Lighter — less code, fewer runs, less noise
│   ├── ⬜ CP8.1: Fewer interruptions
│   └── ⬜ CP8.2: Fewer runs and less code
└── ⬜ CP9: Waits for a need
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

The three features shipped in 0.18.2 on 2026-11-17. The measures get their first value after a week of sessions on the new version.

**Delivers** (3):

- [F9.1: Ledger](../features/F9-record.md#f91-ledger)
- [F9.2: Turn summary](../features/F9-record.md#f92-turn-summary)
- [F9.3: Report](../features/F9-record.md#f93-report)

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

**Status**: 🟨

The user asked on 2026-11-17 for a round of polish and self-test once the features are in. broom is used end to end in fresh sessions, on throwaway repos and on real ones, and what that finds is fixed.

**Delivers** (12):

- [F1.5: Protection list](../features/F1-setup.md#f15-protection-list)
- [I15: The doctor says all is set while TS/JS smells go unmeasured](ISSUES.md#i15-the-doctor-says-all-is-set-while-tsjs-smells-go-unmeasured)
- [I16: A CSS formatter that isn't installed goes unseen outside a JS project](ISSUES.md#i16-a-css-formatter-that-isnt-installed-goes-unseen-outside-a-js-project)
- Fresh sessions used broom end to end on a throwaway repo and on a public Python project, done on 2026-11-18.
  - They met 8 things: the limits card · the setup offer · a block with its fix lines · a fix · an accept with a reason · the turn's summary · the check-up's line · a checked commit.
- A turn-end block no longer takes a commit block's fix line with it, done on 2026-11-18.
- A blocked finding ends with one line in the record: none is lost at a commit of other files, done on 2026-11-18.
- git's own hook reads a linked worktree as it reads the main checkout, done on 2026-11-18.
- A fresh session answers ten questions about a repo from broom alone after five runs, done on 2026-11-17.
- [I1: The moved text doesn't meet the wording rules](ISSUES.md#i1-the-moved-text-doesnt-meet-the-wording-rules)
- README and INSTALL say which systems are supported, done on 2026-11-17.
- An idle turn's end starts git once where it started it 7 times, done on 2026-11-17.
  - An idle hook loads no check.
- A commit with a redirection or a heredoc message is checked where it passed unread before, done on 2026-11-17.

**Exit criteria** (6):

- **Objectives**
  - [O2: Tooling in one conversation](GOALS.md#o2-tooling-in-one-conversation)
  - [O3: Mistakes seen while editing](GOALS.md#o3-mistakes-seen-while-editing)
  - [O7: No script to write](GOALS.md#o7-no-script-to-write): ✅ 2026-11-17, ten of ten answers from broom and no script
- **Thresholds**
  - [T2: An idle Python hook costs 50 ms at most](GOALS.md#t2-an-idle-python-hook-costs-50-ms-at-most): ✅ 2026-11-17, 31 ms for an edit and 39 ms for a turn's end
- **Constraints**
  - [R2: A false positive costs one round](GOALS.md#r2-a-false-positive-costs-one-round): ✅ 2026-11-17
  - [R4: Setup asks at most two questions](GOALS.md#r4-setup-asks-at-most-two-questions): ✅ 2026-11-17

---

## CP7: Nothing is waved through

**Status**: ⬜

The user set this on 2026-11-18: a check that lets Claude carry on puts Claude's speed before the code. Three moments get their own weight, and a finding ends fixed or with a reason the user sees.

**Delivers** (4):

- [F2.10: Check after an edit](../features/F2-sweep.md#f210-check-after-an-edit)
- [F2.11: Nothing is waved through](../features/F2-sweep.md#f211-nothing-is-waved-through)
- [F2.12: A pass is told to the user](../features/F2-sweep.md#f212-a-pass-is-told-to-the-user)
- [F2.13: A turn that changed code shows that tests ran](../features/F2-sweep.md#f213-a-turn-that-changed-code-shows-that-tests-ran)

**Exit criteria** (2):

- **Thresholds**
  - [T5: A check after an edit costs 200 ms at most](GOALS.md#t5-a-check-after-an-edit-costs-200-ms-at-most)
- **Constraints**
  - [R5: Nothing is waved through](GOALS.md#r5-nothing-is-waved-through)

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

**Delivers** (1):

- [F9.4: Tiers by fix rate](../features/F9-record.md#f94-tiers-by-fix-rate)

**Exit criteria** (1):

- **Measures**
  - [M1: Fix rate](GOALS.md#m1-fix-rate) is recorded before and after.

---

### CP8.2: Fewer runs and less code

**Status**: ⬜

**Delivers** (4):

- The test suite runs each file in a process of its own and takes about 40 seconds where it took 150, done on 2026-11-17.
- [I2: Three paths call the same tools](ISSUES.md#i2-three-paths-call-the-same-tools)
- [I5: Five rules sit on an alpha plugin API](ISSUES.md#i5-five-rules-sit-on-an-alpha-plugin-api)
- [I6: The Bash parser guesses what git's hook knows](ISSUES.md#i6-the-bash-parser-guesses-what-gits-hook-knows)

**Exit criteria** (2):

- **Measures**
  - [M2: Check time](GOALS.md#m2-check-time) is lower than at the end of CP2.1.
- **Thresholds**
  - [T2: An idle Python hook costs 50 ms at most](GOALS.md#t2-an-idle-python-hook-costs-50-ms-at-most)

---

## CP9: Waits for a need

**Status**: ⬜

**Delivers** (1):

- [I3: The cause of the reported Stop hang is unconfirmed](ISSUES.md#i3-the-cause-of-the-reported-stop-hang-is-unconfirmed)
