# 048. No rule turns on the clock

Decided: 2026-11-27

---

## The problem

Once a known issue no longer expired, broom still held 8 rules that turned on how much time passed:

| Rule | It was |
|---|---|
| A check that ran out of time | skipped for 20 minutes |
| Background work | waited for half an hour at most |
| Content that passed, and what the measurers found | kept for a day |
| Hotspots and history | the changes of the last 90 days |
| An old TODO | one older than 180 days, by `git blame` |
| A coverage report | its age in days, and behind a commit within a minute's slack |
| `broom report` | the last 30 days, or from a day |
| The ledger, the session folders, the claims and the tools' caches | trimmed by days |

The user set on 2026-11-27 that no rule of broom turns on the clock. Time passing changes no code, so it is no reason to raise a finding again, to stop raising one or to check again.

---

## The choice

What broom holds back waits for an event, and what it trims goes by size or count:

| Rule | Now |
|---|---|
| A check that ran out of time | skipped until the repo's HEAD moves |
| Background work | waited for once per task, by its id. A prompt during a wait keeps the waiting turn's changes, and the next turn's end that is checked ends the wait |
| Content that passed, and what the measurers found | kept while its content, broom's version and the repo's `.broom.json` are the same, the newest 20,000 |
| Hotspots and history | the changes of the last 500 commits, `--commits N` |
| An old TODO | no such counter: the check-up counts TODO comments |
| A coverage report | behind when a code file it covers was written after it |
| `broom report` | the whole record, or from a version of broom with `--since` |
| The ledger | 2 MB, the oldest lines dropped first |
| Session folders, claims, golangci-lint caches, clippy target folders | the 50, 200, 20 and 10 touched last |

Every line of the ledger holds the version of broom that wrote it, from 0.29.0.

3 kinds of reading the clock stay, since none decides by how much time passed:

- **broom's own running time**: a hook run, a tool and a lock wait each have a bound, as [026: A hook run is cut at 30 seconds](026-thirty-second-hook.md) sets. It hides nothing: what a tool cut off would have found is said in a note.
- **A stamp on a record**: when an issue was accepted or a line written, shown or used to order records.
- **The order of two events**: a commit made after the prompt, as [041](041-turn-own-commits.md) reads it, or a file written after a report.

The user confirmed that day that ordering two events is no rule by the clock, since it reads which came first and not how long between them.

`tests/test_no_clock.py` lists every reading of the clock in `lib/broom` with what it is for, and fails on a new one.

---

## Not chosen

- **Keep the windows of statistics**: A total over "the last 90 days" changes with no change to the code, as a rule by the clock does.
- **Drop broom's own running time bound too**: Claude Code ends a hook at its timeout anyway. Without broom's own bound a tool cut off by Claude Code goes on in the background, and nothing says what was skipped.

---

## Consequences

The measures that waited for a week of the ledger wait for a count of checks and findings instead.

A repo that commits often has a shorter history in its hotspots than one that commits rarely. A merge commit is no change of its own, so the 500 commits leave merges out.

Records written before 0.29.0 hold no version, so `broom report --since` counts them as older than any version.
