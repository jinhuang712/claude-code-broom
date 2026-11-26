# 044. An open finding comes back until it ends

Decided: 2026-11-26

---

## The problem

A finding that stopped a commit or a turn's end comes up again only when a later check covers its file. A finding put to the user with `--ask`, or left after three blocks, stays open in the record and leaves Claude's sight once the turns move to other files. On 2026-11-26 the ledger held 328 open findings, 239 of them put to the user, and nothing told Claude about any of them.

The user set the want that day: no problem is hidden, and Claude is reminded of one until it is dealt with.

---

## The choice

broom tells Claude again about every finding that no check has ended, at 2 moments:

- **The next prompt after a question**: the user's answer has come, so Claude is told the findings it asked about, to fix them or to accept them with `--agreed`.
- **A session's start in the repo**: Claude is told the findings still open there, asked about or not.

Before it tells, broom checks the files of those findings again with the rules of the day. A finding no longer there is recorded as fixed and is not told, so a rule changed since or a fix made by hand makes no noise.

It tells and never blocks. The finding still blocks wherever a check covers its file, as before.

The user set that it is built once [CP8: Lighter](../../plan/ROADMAP.md#cp8-lighter) has its numbers, so that the fix rate of that week is measured without it.

---

## Not chosen

- **At the next prompt alone**: A finding left in another session is never told again.
- **At a session's start alone**: Claude is not told when the user's answer comes.
- **Every turn's end blocks again on every open finding**: It judges code the turn didn't touch, against [Only what changed](../../PHILOSOPHY.md#how-much-of-the-code-does-a-check-judge), and it interrupts every turn.
- **Tell without checking again**: Findings that a changed rule no longer finds would be told as noise, and noise teaches Claude to override broom.

---

## Consequences

The check again costs time at a session's start, in the scan that already runs in the background there.

A finding whose file is gone leaves the record with no line, as before, and is not told.
