# Check-up

This part looks for rot: numbers that get worse with no one change at fault. It exists because a check on a change can't see what piled up across a hundred changes.

```
session start ─▶ the smell scan of HEAD (async, cached) ─┐
                 one pass over the files' text ──────────┼─▶ the counters ─▶ compare with the last check-up
                 the coverage report, if there is one ───┤                        │
                                                          │        grew ──────────┴─▶ one line to Claude, once
                                                          └─▶ the record of this repo, in the data directory
```

---

## The counters

8 counters, per repo:

- Lint suppressions.
- Skipped tests.
- TODO comments older than 180 days.
- Dead-code findings in the whole repo.
- Public code with no doc comment.
- Calls to deprecated APIs.
- Duplicate test blocks.
- Lines no test reaches.

The first three come from the one pass over the files' text that `broom stats` makes. The next four come from the smell scan's own results. The last comes from the coverage report a test run left, and it is left out when there is none. No tool runs for the check-up.

The smell scan's jscpd run already finds the clones between two test files. The checks on a change drop them, and the scan keeps them apart for this counter. Each block is counted once, on the side that was written last, since the copy is likelier there.

A counter whose tool is missing, failed or timed out is left out of that check-up: it is neither compared nor recorded. A low count from a tool that didn't run would read as a fall, and then as growth when the tool is back.

---

## When it speaks

The check-up runs in the async session scan, after the smell scan, also when the scan of HEAD was cached. The first numbers of a repo are taken silently as its baseline, and so are the first after an update of broom, since another version may count other things. A repo and its linked worktrees share one record.

When a counter is higher than at the last check-up, Claude is told once, in one line, with the old and the new value, up to three files that added to it and the command that shows where each number sits. The new numbers then become the record, so the same growth is told once. A counter that fell is recorded silently.

A hook with less than 6 seconds left skips the check-up until the next session. A repo of more than 5,000 files is not scanned at session start, so it gets no check-up there.

`smells_off` holding `checkup` turns it off, and so does the `smells` setting at `off`.

---

## In the diagnosis

`broom diagnose` lists every counter with its value now and at the last check-up, whether it grew or not. Narrowed to paths it counts only those and shows no last value. It never writes the record.

The age of a TODO comes from `git blame` on at most 200 lines, so in a repo with more TODO lines that counter is a floor.
