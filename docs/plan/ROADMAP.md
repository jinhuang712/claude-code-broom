# Roadmap

**Current checkpoint**: [CP1: 0.18.1 reaches users](#cp1-0181-reaches-users). The work is done and sits on the local `main`, and the push waits for an answer.

---

## Summary

```
Roadmap
├── 🟨 CP1: 0.18.1 reaches users — the hook limits and the docs set are released
├── ⬜ CP2: Nothing passes silently — every pass leaves a reason the user sees
│   ├── ⬜ CP2.1: The ledger
│   └── ⬜ CP2.2: Reasons and self-waivers
├── ⬜ CP3: Claude knows how to fix — the bar before the work, the fix beside the finding
│   ├── ⬜ CP3.1: Messages that say how to fix
│   └── ⬜ CP3.2: Limits told before the work
├── ⬜ CP4: A refactoring kit — a full diagnosis, the worst places first, the numbers after
├── ⬜ CP5: A check-up for rot — numbers that speak when they grow
│   ├── ⬜ CP5.1: Counters, dead code and comments
│   ├── ⬜ CP5.2: Tests: coverage, duplicates and skips
│   └── ⬜ CP5.3: Dependencies and deprecated APIs
├── ⬜ CP6: Lighter — less code, fewer runs, less noise
│   ├── ⬜ CP6.1: Fewer interruptions
│   ├── ⬜ CP6.2: Fewer runs and less code
│   └── ⬜ CP6.3: Docs and setup that say what is so
└── ⬜ CP7: Waits for a need
```

---

## CP1: 0.18.1 reaches users

**Status**: 🟨

Versions 0.18.0 and 0.18.1 and the docs set are committed locally. Nothing is pushed or tagged. The open question is [Who pushes and tags a release?](TODO.md#p1discussion-who-pushes-and-tags-a-release).

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

**Status**: ⬜

broom keeps no record of what it stopped and what was fixed, so nobody can say whether it works. This checkpoint gives it a record and makes every pass carry a reason.

**Exit criteria** (2):

- **Sub-checkpoints**
  - [CP2.1: The ledger](#cp21-the-ledger) is met.
  - [CP2.2: Reasons and self-waivers](#cp22-reasons-and-self-waivers) is met.

---

### CP2.1: The ledger

**Status**: ⬜

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

**Status**: ⬜

**Delivers** (3):

- [F2.5.3: A reason for every pass](../features/F2-sweep.md#f253-a-reason-for-every-pass)
- [F2.8: Self-waivers shown](../features/F2-sweep.md#f28-self-waivers-shown)
- [F2.4.1: Offered at setup](../features/F2-sweep.md#f241-offered-at-setup)

**Exit criteria** (2):

- **Objectives**
  - [O4: Nothing passes silently](GOALS.md#o4-nothing-passes-silently)
- **Constraints**
  - [R2: A false positive costs one round](GOALS.md#r2-a-false-positive-costs-one-round)

---

## CP3: Claude knows how to fix

**Status**: ⬜

A block says what is over a limit and not what to do about it. This checkpoint puts the fix beside the finding and the bar before the work.

**Exit criteria** (2):

- **Sub-checkpoints**
  - [CP3.1: Messages that say how to fix](#cp31-messages-that-say-how-to-fix) is met.
  - [CP3.2: Limits told before the work](#cp32-limits-told-before-the-work) is met.

---

### CP3.1: Messages that say how to fix

**Status**: ⬜

**Delivers** (1):

- [F2.9: Messages that say how to fix](../features/F2-sweep.md#f29-messages-that-say-how-to-fix)

**Exit criteria** (1):

- **Measures**
  - [M1: Fix rate](GOALS.md#m1-fix-rate) is recorded before and after.

---

### CP3.2: Limits told before the work

**Status**: ⬜

**Delivers** (1):

- [F4.8: Limits told before the work](../features/F4-smells.md#f48-limits-told-before-the-work)

**Exit criteria** (1):

- **Measures**
  - [M1: Fix rate](GOALS.md#m1-fix-rate) is recorded before and after.

---

## CP4: A refactoring kit

**Status**: ⬜

A refactor starts from numbers: what is in the repo, where it hurts most and whether the work paid off.

**Delivers** (4):

- [F10.1: Whole-repo diagnosis](../features/F10-diagnosis.md#f101-whole-repo-diagnosis)
- [F10.2: Hotspots by churn](../features/F10-diagnosis.md#f102-hotspots-by-churn)
- [F10.3: Before and after](../features/F10-diagnosis.md#f103-before-and-after)
- [I4: The tests write into the real data directory](ISSUES.md#i4-the-tests-write-into-the-real-data-directory)

**Exit criteria** (1):

- **Objectives**
  - [O5: A full diagnosis of an old repo](GOALS.md#o5-a-full-diagnosis-of-an-old-repo)

---

## CP5: A check-up for rot

**Status**: ⬜

Rot is what gets worse with no one change at fault. The check-up counts it across the repo and speaks when a number grew.

**Exit criteria** (3):

- **Sub-checkpoints**
  - [CP5.1: Counters, dead code and comments](#cp51-counters-dead-code-and-comments) is met.
  - [CP5.2: Tests: coverage, duplicates and skips](#cp52-tests-coverage-duplicates-and-skips) is met.
  - [CP5.3: Dependencies and deprecated APIs](#cp53-dependencies-and-deprecated-apis) is met.

---

### CP5.1: Counters, dead code and comments

**Status**: ⬜

**Delivers** (4):

- [F11.1: Counters](../features/F11-checkup.md#f111-counters)
- [F11.4: Dead code in the whole repo](../features/F11-checkup.md#f114-dead-code-in-the-whole-repo)
- [F11.5: Missing comments](../features/F11-checkup.md#f115-missing-comments)
- [F4.2.1: Broad catch](../features/F4-smells.md#f421-broad-catch)

**Exit criteria** (1):

- **Objectives**
  - [O6: A number that got worse is told once](GOALS.md#o6-a-number-that-got-worse-is-told-once)

---

### CP5.2: Tests: coverage, duplicates and skips

**Status**: ⬜

**Delivers** (3):

- [F11.2: Test coverage](../features/F11-checkup.md#f112-test-coverage)
- [F11.3: Duplicate tests](../features/F11-checkup.md#f113-duplicate-tests)
- [F4.2.2: Skipped test](../features/F4-smells.md#f422-skipped-test)

**Exit criteria** (1):

- **Objectives**
  - [O6: A number that got worse is told once](GOALS.md#o6-a-number-that-got-worse-is-told-once)

---

### CP5.3: Dependencies and deprecated APIs

**Status**: ⬜

**Delivers** (2):

- [F11.6: Dependencies](../features/F11-checkup.md#f116-dependencies)
- [F11.7: Deprecated APIs](../features/F11-checkup.md#f117-deprecated-apis)

**Exit criteria** (1):

- **Objectives**
  - [O6: A number that got worse is told once](GOALS.md#o6-a-number-that-got-worse-is-told-once)

---

## CP6: Lighter

**Status**: ⬜

The ledger's numbers say which rule is noise and which tool is slow. This checkpoint cuts by them.

**Exit criteria** (3):

- **Sub-checkpoints**
  - [CP6.1: Fewer interruptions](#cp61-fewer-interruptions) is met.
  - [CP6.2: Fewer runs and less code](#cp62-fewer-runs-and-less-code) is met.
  - [CP6.3: Docs and setup that say what is so](#cp63-docs-and-setup-that-say-what-is-so) is met.

---

### CP6.1: Fewer interruptions

**Status**: ⬜

**Delivers** (1):

- [F9.4: Tiers by fix rate](../features/F9-record.md#f94-tiers-by-fix-rate)

**Exit criteria** (1):

- **Measures**
  - [M1: Fix rate](GOALS.md#m1-fix-rate) is recorded before and after.

---

### CP6.2: Fewer runs and less code

**Status**: ⬜

**Delivers** (3):

- [I2: Three paths call the same tools](ISSUES.md#i2-three-paths-call-the-same-tools)
- [I5: Four rules sit on an alpha plugin API](ISSUES.md#i5-four-rules-sit-on-an-alpha-plugin-api)
- [I6: The Bash parser guesses what git's hook knows](ISSUES.md#i6-the-bash-parser-guesses-what-gits-hook-knows)

**Exit criteria** (2):

- **Measures**
  - [M2: Check time](GOALS.md#m2-check-time) is lower than at the end of CP2.1.
- **Thresholds**
  - [T2: An idle Python hook costs 50 ms at most](GOALS.md#t2-an-idle-python-hook-costs-50-ms-at-most)

---

### CP6.3: Docs and setup that say what is so

**Status**: ⬜

**Delivers** (3):

- [F1.5: Protection list](../features/F1-setup.md#f15-protection-list)
- [I1: The moved text doesn't meet the wording rules](ISSUES.md#i1-the-moved-text-doesnt-meet-the-wording-rules)
- [I7: The docs don't say which systems are supported](ISSUES.md#i7-the-docs-dont-say-which-systems-are-supported)

**Exit criteria** (1):

- **Objectives**
  - [O2: Tooling in one conversation](GOALS.md#o2-tooling-in-one-conversation)

---

## CP7: Waits for a need

**Status**: ⬜

**Delivers** (2):

- [F8.3: Rust](../features/F8-languages.md#f83-rust), with the smells it lacks.
- [I3: The cause of the reported Stop hang is unconfirmed](ISSUES.md#i3-the-cause-of-the-reported-stop-hang-is-unconfirmed)
