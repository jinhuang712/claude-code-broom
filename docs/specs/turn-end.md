# Turn end

The turn-end check lints and type-checks what a turn changed when Claude stops. It exists because a commit hook never sees work the user commits by hand or through a wrapper.

```
prompt ─▶ note the working tree and HEAD (async)
edits  ─▶ record each file, a subagent's under its own id
stop   ─▶ background work running? ─ yes ─▶ wait for the turn it wakes
              │ no
              ▼
          the turn's files ─▶ check ─▶ block once, or end the turn
```

---

## What the turn changed

Edit and Write are recorded as they happen. A Bash command can rewrite files too, and a wrapper can commit them. An async prompt hook notes the changed code files by modification time and size, and HEAD. The turn's end adds what changed since and what was committed since, and measures it all against that HEAD. A commit made during the turn still shows as the turn's change. A turn that changed no code ends after that one look at the tree.

A many-file edit through Serena names no files, so the turn's end takes the repo's changed files instead.

- [020: The turn's changes come from a snapshot at the prompt](decisions/020-turn-snapshot.md)

---

## Pauses

A Stop hook fires whenever Claude finishes responding, not only when the work is done. The check waits while any background task runs and checks at the turn that work wakes. It gives up the wait after half an hour.

A turn in plan mode is not checked.

- [019: The turn-end check waits for background work](decisions/019-wait-for-background.md)

---

## Blocking once

Findings block the turn's end with the same report as a commit. A hint blocks here too, once, so Claude cleans up now. The block is also kept as the repo's last blocked result, so `broom known --accept` serves a turn's end as it serves a commit. What a commit blocked before stays behind it in that record, for a later commit to fix.

Stopping again without a new edit ends the turn. It records nothing as known: what is left stays open, is written to the record and shows in the turn's summary, and a commit still stops on it. After three blocks the check gives up in the same way.

---

## Subagents

Hooks run inside subagents too, with an agent id. A subagent's edits are recorded under it, and its own end checks them. The block goes to the subagent as its next instruction.

- [021: A subagent's end checks its own edits](decisions/021-subagent-own-end.md)
