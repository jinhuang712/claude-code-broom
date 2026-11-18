# Issues

---

## Summary

```
Issues
├── docs
│   └── I1: The moved text doesn't meet the wording rules
├── refactor
│   ├── I2: Three paths call the same tools
│   ├── I5: Five rules sit on an alpha plugin API
│   └── I6: The Bash parser guesses what git's hook knows
└── fix
    ├── I3: The cause of the reported Stop hang is unconfirmed
    └── I8: A hole in the record
```

---

## I1: The moved text doesn't meet the wording rules

- type: docs
- why:
  - The changelog's sections before 0.18.2 keep their old wording, with long bullets of several commas.
  - README has no hero image.
- found: the docs pass, 2026-11-17
- next: [A hero image for the README](TODO.md#p1discussion-a-hero-image-for-the-readme)

---

## I2: Three paths call the same tools

- type: refactor
- why:
  - The lint check, the scratch copy and the real tree each start the same linters on the same files.
  - A cache keeps the base of a change from being measured twice, and the rest still runs more than once.
- found: a review of the hooks' cost, 2026-11-16
- touches:
  - [F2.1: Commit check](../features/F2-sweep.md#f21-commit-check)
  - [F4: Smells](../features/F4-smells.md)
- next: the ledger's seconds per tool, to say which run to keep

---

## I3: The cause of the reported Stop hang is unconfirmed

- type: fix
- why:
  - A Stop hook ran until Claude Code ended it at its timeout, 18 times in one session.
  - 0.18.1 removed every wait that had no bound.
  - The hang didn't reproduce here, so the cause on that machine is not known.
- found: a user's report, 2026-11-16
- touches:
  - [F2.7: Time limit](../features/F2-sweep.md#f27-time-limit)
- next: a `hook-trace.log` from the machine where it happened

---

## I5: Five rules sit on an alpha plugin API

- type: refactor
- why:
  - 5 smells in TS/JS come from rules of broom's own: `bool_params` · `type_lines` · `globals` · `commented_code` · `missing_docs`.
  - They load through oxlint's JS plugins, which oxlint's docs call alpha.
  - They need Node.
- found: a review of what broom wrote itself, 2026-11-17
- touches:
  - [F4.2: Occurrence smells](../features/F4-smells.md#f42-occurrence-smells)
- next: the fix rate of these five rules, to say whether to move them to another tool or drop them

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

## I8: A hole in the record

- type: fix
- why: A turn-end block replaces a commit block's entry for the same repo, which can drop the earlier block's fix line.
- found: the review of 0.19.0, 2026-11-17
- touches:
  - [F9.1: Ledger](../features/F9-record.md#f91-ledger)
