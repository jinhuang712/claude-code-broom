# Issues

---

## Summary

```
Issues
├── docs
│   └── I1: The moved text doesn't meet the wording rules
├── refactor
│   ├── I2: Three paths call the same tools
│   ├── I5: Four rules sit on an alpha plugin API
│   └── I6: The Bash parser guesses what git's hook knows
└── fix
    ├── I3: The cause of the reported Stop hang is unconfirmed
    ├── I8: Two holes in the record
    ├── I10: No fresh session has used broom end to end
    └── I12: A fresh session finishes four of ten answers by hand
```

---

## I1: The moved text doesn't meet the wording rules

- type: docs
- why: The docs pass moved text into the new docs and kept much of its wording. Bullets with several commas remain. CHANGELOG's sections are dated and not yet grouped by area. README has no hero image and no architecture diagram.
- found: the docs pass, 2026-11-17

---

## I2: Three paths call the same tools

- type: refactor
- why: The lint check, the scratch copy and the real tree each start the same linters on the same files. A cache keeps the base of a change from being measured twice, and the rest still runs more than once.
- found: a review of the hooks' cost, 2026-11-16
- touches:
  - [F2.1: Commit check](../features/F2-sweep.md#f21-commit-check)
  - [F4: Smells](../features/F4-smells.md)
- next: the ledger's seconds per tool, to say which run to keep

---

## I3: The cause of the reported Stop hang is unconfirmed

- type: fix
- why: A Stop hook ran until Claude Code ended it at its timeout, 18 times in one session. 0.18.1 removed every wait that had no bound, and the hang didn't reproduce here, so the cause on that machine is not known.
- found: a user's report, 2026-11-16
- touches:
  - [F2.7: Time limit](../features/F2-sweep.md#f27-time-limit)
- next: a `hook-trace.log` from the machine where it happened

---

## I5: Four rules sit on an alpha plugin API

- type: refactor
- why: `bool_params`, `type_lines`, `globals` and `commented_code` in TS/JS come from rules of broom's own, loaded through oxlint's JS plugins. oxlint's docs call that feature alpha, and it needs Node.
- found: a review of what broom wrote itself, 2026-11-17
- touches:
  - [F4.2: Occurrence smells](../features/F4-smells.md#f42-occurrence-smells)
- next: the fix rate of these four rules, to say whether to move them to another tool or drop them

---

## I6: The Bash parser guesses what git's hook knows

- type: refactor
- why: The commit hook reads a Bash command to predict the files a commit will take. git's own hook sees the staged files. The parser can go once git's hook is the norm and formatting at commit has another moment.
- found: a review of what broom wrote itself, 2026-11-17
- touches:
  - [F2.1: Commit check](../features/F2-sweep.md#f21-commit-check)
  - [F2.4: git's pre-commit hook](../features/F2-sweep.md#f24-gits-pre-commit-hook)
- next: [F2.4.1: Offered at setup](../features/F2-sweep.md#f241-offered-at-setup)

---

## I8: Two holes in the record

- type: fix
- why: A turn-end block replaces a commit block's entry for the same repo, which can drop the earlier block's fix line. A self-waiver is missed when every file's content had already passed and `.broom.json` wasn't edited through Edit or Write.
- found: the review of 0.19.0, 2026-11-17
- touches:
  - [F9.1: Ledger](../features/F9-record.md#f91-ledger)
  - [F2.8: Self-waivers shown](../features/F2-sweep.md#f28-self-waivers-shown)

---

## I10: No fresh session has used broom end to end

- type: fix
- why: The test suite drives the hooks with made-up input. On 2026-11-17 a fresh session on a throwaway repo met the limits card, the setup offer, the smell note, a turn-end block with its fix lines, a fix and the turn's summary. Three things are still unmet by a fresh session: an accept with a reason, the check-up after a counter grew, and a change with a commit on a real repo.
- found: the user's request for a self-test, 2026-11-17
- touches:
  - [F1.3: /broom:setup](../features/F1-setup.md#f13-broomsetup)
  - [F2.9: Messages that say how to fix](../features/F2-sweep.md#f29-messages-that-say-how-to-fix)
  - [F9.2: Turn summary](../features/F9-record.md#f92-turn-summary)

---

## I12: A fresh session finishes four of ten answers by hand

- type: fix
- why: A fresh session asked ten questions on a throwaway repo ran `broom stats` and `broom smells`, and never `broom diagnose`. It ran a linter itself for the doc comments and the deprecated calls, counted the third to fifth longest functions by hand, read each old TODO's date with `git blame` and checked the coverage report with a one-line script. Since then the session's note says what `broom diagnose` holds, the longest functions are listed under the limit too, and the oldest TODOs come with their dates. Two things are left: no fresh session has run since, and doc comments missing in TS/JS are not counted.
- found: the second fresh-session self-test, 2026-11-17
- touches:
  - [F10.4: Numbers on request](../features/F10-diagnosis.md#f104-numbers-on-request)
  - [F10.5: Claude knows what to ask](../features/F10-diagnosis.md#f105-claude-knows-what-to-ask)
  - [F11.5: Missing comments](../features/F11-checkup.md#f115-missing-comments)
