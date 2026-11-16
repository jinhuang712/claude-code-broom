# F9: Record

```
F9: Record
├── F9.1: Ledger — every block, fix, pass and skip leaves a line
├── F9.2: Turn summary — the user sees what was let through
├── F9.3: Report — what broom stopped, what was fixed and what passed
└── F9.4: Tiers by fix rate — a rule nobody fixes stops interrupting
```

The record says what broom did with each finding. The user ends up knowing whether broom works: how much it stopped, how much of that was fixed and what went through with which reason.

- **Stance**: [Say what happened](../PHILOSOPHY.md#what-happens-to-what-was-skipped)

---

## F9.1: Ledger

Every block, fix, pass and skip is written as one line: when, which repo, which rule, which file and how it ended. A finding counts as fixed when a block is followed by content that passes.

The ledger also notes how many seconds each tool took in each check.

---

## F9.2: Turn summary

When a turn let something through, the user sees one line at its end, such as "broom let 3 through: 2 magic numbers, 1 long function". A turn that let nothing through says nothing.

---

## F9.3: Report

One command prints the record of a repo over a period: findings blocked, fixed and let through, by rule, with the reasons given.

---

## F9.4: Tiers by fix rate

A rule that is let through far more often than it is fixed is told to Claude without stopping the turn. The user is told when a rule changes tier. A rule that is nearly always fixed stays as it is.

It applies to hints only. A type error and a severe smell never change tier.

- **Design**: [6. A false positive costs one round](../DESIGNS.md#6-a-false-positive-costs-one-round)
