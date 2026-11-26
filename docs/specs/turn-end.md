# Turn end

The turn-end check lints and type-checks what a turn changed when Claude stops. It exists because a commit hook never sees work the user commits by hand or through a wrapper.

```
prompt ─▶ note the working tree and HEAD (async)
edits  ─▶ record each file, a subagent's under its own id
stop   ─▶ background work running? ─ yes ─▶ wait for the turn it wakes
              │ no
              ▼
          the turn's files ─▶ check ─▶ block, or end the turn
```

---

## What the turn changed

Edit and Write are recorded as they happen. A Bash command can rewrite files too, and a wrapper can commit them. An async prompt hook notes the changed code files by modification time and size, HEAD and the second it looked. The turn's end adds what changed since and the files of the commits made since, and measures it all against that HEAD. A commit made during the turn still shows as the turn's change. A turn that changed no code ends after that one look at the tree. An edited file git ignores is left out, by one `git check-ignore` per repo.

A commit made before that second is not the turn's, though the turn may bring it in by a pull, a reset or a landing of earlier work. Its files are left out, and the turn's change is measured from the newest such commit on HEAD's first-parent line. A merge counts only the files it resolved.

A many-file edit through Serena names no files, so the turn's end takes the repo's changed files instead.

- [020: The turn's changes come from a snapshot at the prompt](decisions/020-turn-snapshot.md)
- [041: A commit counts as the turn's when it was made after the prompt](decisions/041-turn-own-commits.md)

---

## Pauses

A Stop hook fires whenever Claude finishes responding, not only when the work is done. The check waits while background work runs and checks at the turn that work wakes. It waits once for each task, told apart by its id: a task an earlier turn's end already waited for, still running at a later one, holds nothing, so a server left running doesn't keep every turn's end unchecked. A prompt during a wait starts no new snapshot: the waiting turn's changes, Bash's too, are checked at the next turn's end that is checked, which ends the wait.

A turn in plan mode is not checked.

- [019: The turn-end check waits for background work](decisions/019-wait-for-background.md)

---

## Blocking

Findings block the turn's end with the same report as a commit, a hint with the rest. The block is also kept as the repo's last blocked result, so `broom known --accept` serves a turn's end as it serves a commit. What a commit blocked before stays behind it in that record, for a later commit to fix.

Stopping again passes nothing: each stop checks again, with a new edit or without, and blocks while a finding is left. After three blocks the check gives up. It records nothing as known: what is left stays open and is written to the record as `gave-up`, and a commit still stops on it. The repo's last blocked result lets go of it then, so a later `broom known --accept` can't pass it a second time. The user's line opens with `broom GAVE UP after 3 blocks` and names up to five of the findings left.

A nit never blocks. The user's line at the turn's end tells it, once.

---

## Tests ran

A turn that changed code has work left over when a code file it changed holds content no test run tested, or when the last test run failed. The turn's end raises it as one finding, where the repo tracks a test file.

The trace comes from two hooks. The hook before each Bash command notes a command that is a test run, with the time. A hook on the event Claude Code fires after a command that didn't exit 0 notes one that failed, with the first line of its error. A test run with no failure after it counts as passed. Both notes sit in the session's directory, so a subagent's test run counts for the main session.

A test run's note holds what it tested: the commit of the repo it ran in, and the blob of each code file that differed from that commit. A file the turn changed counts as tested when a run that didn't fail tested its content as it is now. So a file tested in a linked worktree and then merged into the main checkout counts, and so does a file that was only touched. The finding names up to three files that are not tested. A file the turn deleted needs no test.

An accept of the finding is kept in the turn's directory and not among the known issues, so it holds for that turn only.

- [034: A test run is known by the hook events of its command, and its accept holds for one turn](decisions/034-test-run-by-hook-events.md)

---

## Asking the user

Ending the turn is how Claude asks the user anything, so a block would keep a question from being put. `broom known --ask "<question>"` marks what the last block showed as waiting for the user, in the turn it was blocked in. The turn's end leaves those findings out of its block for that turn and opens the user's line with the question. They stay in the repo's last blocked result, so an accept still serves them once the user has answered. A later turn's end blocks on them like any other finding, but only when that turn changed their file: a turn that changes nothing, or only other files, ends without them. A commit of their file is denied until they are fixed or accepted.

The question leaves a mark in the session's directory. The next prompt holds the user's answer, so a synchronous hook tells Claude then which findings it asked about, from the record, and the async prompt hook checks their files again: one found gone is recorded as fixed and told as gone on a later turn. Without the mark, the synchronous hook is a shell test that exits before Python starts.

- [033: A turn can end with a question to the user, which passes nothing](decisions/033-ask-the-user.md)
- [044: An open finding comes back until it ends](decisions/044-open-findings-come-back.md)

---

## Subagents

Hooks run inside subagents too, with an agent id. A subagent's edits are recorded under it, and its own end checks them. The block goes to the subagent as its next instruction.

- [021: A subagent's end checks its own edits](decisions/021-subagent-own-end.md)
