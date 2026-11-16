# Record

This part writes down what broom did with each finding and reads it back. It exists because a finding that was fixed left no trace, so nobody could say whether the checks work.

```
a commit or a turn's end is checked
  ├── blocked ──────────────▶ block line, one per finding
  ├── an earlier block's finding is gone ─▶ fix line, when the check really covered it
  ├── let through ──────────▶ pass line with how, and a note in the turn's directory
  ├── a tool didn't run ────▶ skip line
  └── each check ───────────▶ time line
                                    │
ledger.jsonl ◀──────────────────────┘        the turn's end ─▶ one line for the user
     └──▶ broom report
```

---

## The ledger

The ledger is `ledger.jsonl` in the data directory, one JSON object per line. Every line holds the time, the repo, the event and the hook it came from. The repo is the main worktree's root, so a repo and its linked worktrees share one record. A file is given relative to its own worktree's root.

7 events:

- **block**: A finding stopped a commit or a turn's end.
- **fix**: A finding of an earlier block is gone.
- **pass**: A finding was let through, with how.
- **hint**: A smell hint was given as context without a block.
- **skip**: A tool didn't run, with the timeout or missing-tool note.
- **time**: The seconds one check took in a hook.
- **error**: A hook failed and let the action through.

A pass says how it went through, in 6 ways:

- **retry**: The same lint result was committed again.
- **denials**: A lint result passed after three denials.
- **accept**: Claude ran `broom known --accept`, and the line keeps the reason.
- **stop-again**: The turn ended by stopping again, and the finding is now known.
- **turn-ended**: A type error or a severe smell was still there when the turn ended by stopping again.
- **gave-up**: The turn-end check gave up after three blocks.

Writing is one append under a lock. It never raises into a hook. Over 2 MB the lines older than 90 days are dropped, then the oldest ones down to 1.5 MB.

---

## When a fix counts

A finding is fixed when it was in the last block of the same repo, or of the same turn, and is gone from the current result. Three things keep a gone finding open instead:

- Its file is not among the files this check covered, as when the next commit takes other files.
- A timeout or missing-tool note covers the tool that found it.
- Another finding of the same file, tool and rule is new: the finding changed its key and is still there, as a function cut from 120 lines to 110.

A type error in a file outside the checked files is never counted as fixed.

---

## The turn summary

Each pass is also noted in the turn's directory. When the turn ends, the notes become one line for the user, grouped by rule and by how, such as `broom let 3 through this turn: 2 magic_numbers (retry), 1 function_lines (accepted: <why>)`. What the stop itself left is appended to the same line. A turn that let nothing through says what it said before.

The notes are cleared at the next prompt. With `check_on` at `commit` no stop hook ends the turn, so no summary is shown. A pass in git's own pre-commit hook belongs to no turn and is not shown either.

---

## The report

`broom report` counts distinct findings by repo and key, each by how it ended last: fixed, let through or still open. A finding blocked three times and then fixed counts once as blocked and once as fixed.

The fix rate is the fixed over the fixed plus the let through, so a finding that hasn't ended counts against no rule. Hint lines are written and not yet shown.
