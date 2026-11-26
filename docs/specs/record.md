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

10 events:

- **block**: A finding stopped a commit or a turn's end.
- **fix**: A finding of an earlier block is gone.
- **pass**: A finding was let through, with how.
- **ask**: A question about a blocked finding was put to the user. It is no outcome, and the finding stays open.
- **hint**: A nit, which is a slight smell, was told without a block. The event keeps its older name.
- **waiver**: A change loosened the bar, with its kind.
- **skip**: A tool didn't run, with the timeout or missing-tool note.
- **time**: The seconds one tool took in a hook.
- **run**: The seconds a whole check of a commit or a turn's end took, once it ran a tool: lint, types and smells. Content that passed before runs no tool and writes none.
- **error**: A hook failed and let the action through.

A pass says how it went through, in 2 ways:

- **accept**: Claude ran `broom known --accept`, and the line keeps the reason. With `--agreed` it also says that the user agreed.
- **gave-up**: The turn-end check gave up after three blocks. The finding is not known.

Older lines can hold four more: `retry`, `denials` and `stop-again` from before 0.19.0, and `turn-ended` from before 0.23.5.

A waiver has one of 3 kinds:

- **config**: The repo's `.broom.json` is looser than at the base in 1 of 5 ways: a smell turned off · a glob added to `exclude` or `legacy` · a command added to `test_commands` · a limit raised · `check_on` or `smells` set to off.
- **suppression**: A comment on a line the change added holds a lint suppression, with a reason or without, or a Rust `allow` attribute does. The comment comes from the file's syntax tree, so a marker inside a string is none.
- **no-verify**: Claude ran `git commit --no-verify`.

The same waiver seen again in one turn is written once. An edit of `.broom.json` is noted at once, since a `check_on` set to off would keep every later check from seeing it. The turn's snapshot holds the file too, so the turn's end notes one that a command changed or committed.

Writing is one append under a lock. It never raises into a hook. Over 2 MB the lines older than 90 days are dropped, then the oldest ones down to 1.5 MB.

---

## When a fix counts

A finding is fixed when a block of the same repo or of the same turn held it, no check has ended it and it is gone from the current result. A turn-end block takes the place of the repo's last block, and what a commit blocked before stays behind it until a commit covers its file. A fix is written once: a commit and a turn's end that both see a finding gone write one line between them.

Four things keep a gone finding open instead:

- Its file is not among the files this check covered, as when the next commit takes other files.
- A timeout or missing-tool note covers the tool that found it.
- Another finding with the same file, tool and rule is new: the old one changed its key and is still there.
  - A function cut from 120 lines to 110 is such a case.
- The same run saw a looser `.broom.json`, which may only have hidden it.

A type error in a file outside the checked files is never counted as fixed.

A commit keeps what earlier commits blocked in files it didn't take. Such a finding stays in the repo's record until a commit covers its file, it is accepted or its file is gone. One whose file is gone leaves with no line, since a moved file would otherwise read as fixed.

---

## The turn summary

Each pass is also noted in the turn's directory. When the turn ends, the notes become one line for the user, grouped by rule and by how, such as `broom let 3 through this turn: 2 bool_params (gave-up), 1 function_lines (accepted: <why>)`. A finding the user agreed to is shown as `accepted, the user agreed`. The turn's self-waivers follow on the same line, then what the stop itself left.

Three things open the line ahead of the summary, in this order: a question put with `--ask`, a give-up, and 3 or more accepts that Claude made on its own. A turn with only waivers says `broom saw 2 self-waivers this turn: ...`. A turn with neither says what it said before.

The notes are cleared at the next prompt. With `check_on` at `commit` no stop hook ends the turn, so no summary is shown. A pass in git's own pre-commit hook belongs to no turn and is not shown either.

---

## The report

`broom report` counts distinct findings by repo and key, each by how it ended last: fixed, let through or still open. A finding blocked three times and then fixed counts once as blocked and once as fixed.

The fix rate is the fixed over the fixed, the let through and the still open that the user was asked about. A question that nothing ended counts against its rule, since the code still holds the finding, and it stays among the open ones, as `38 (asked 36)`. A finding still open that nobody asked about counts against no rule. A block of self-waivers gives their count by kind and the notes of the config ones. The lines of nits are written and not yet shown.

The run lines give the seconds of a whole check, grouped by moment: git's hook and Claude Code's commit hook are both at a commit, and a subagent's end is at a turn's end. The time lines give the seconds per tool beside them. Before 0.25.10 the ledger held only the time lines, which leave out the smells.

Without paths and with `--all`, a repo in a temporary folder is left out: the system's temporary folder, `/tmp` and `/var/folders`, as given and resolved. The first line says how many were left out.

- [043: A question that nothing ended counts against its rule](decisions/043-asked-findings-count-against-the-rate.md)
