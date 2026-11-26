# F5: Cleanup

```
F5: Cleanup
├── F5.1: Ranking — the smells of a repo or an area, worst first
├── F5.2: Session note — Claude raises severe smells at a natural point
└── F5.3: Cleanup on the user's word — small verified batches, worst first
```

Cleanup goes after the smells already in a repo, which the checks on a change never raise. The user ends up with a ranked list and, when they agree, a cleanup worst first.

---

## F5.1: Ranking

`broom smells` lists the hotspot files, ranked by their smells and by how often they change, and the worst smells, furthest past their limit first. It covers the whole repo or some paths, and says how many more there are.

With `--base REV` it lists only what the changes since that revision made worse. Missing tools are named in the first line, where counts without them read as cleaner than the code is. A smell the user decided to keep and that was accepted as known is left out, and the last line says how many.

- **Commands**: [broom smells](../CLI.md#broom-smells)
- **How it works**: [Cleanup](../specs/cleanup.md)

**Stories** (1):

- A user about to rework an area ranks its smells first to see which files are worst.

---

## F5.2: Session note

When a repo has smells past the hard limit, broom tells Claude at the start of a session. Claude raises them at a natural point and offers a cleanup. It doesn't interrupt the user's task and doesn't clean up without their go-ahead.

When the user says not now, Claude runs `broom smells --dismiss`, and the note stays quiet until the count grows. A repo of more than 5,000 files is not scanned at session start.

- **Design**: [7. Nothing is installed or set without a yes](../DESIGNS.md#7-nothing-is-installed-or-set-without-a-yes)
- **Commands**: [broom smells](../CLI.md#broom-smells)
- **How it works**: [Cleanup](../specs/cleanup.md)
- **Why**:
  - [017: The session scan runs in an async hook](../specs/decisions/017-async-session-scan.md)
  - [018: broom offers a cleanup and never starts one](../specs/decisions/018-offer-cleanup.md)

---

## F5.3: Cleanup on the user's word

A cleanup starts when the user asks for one in their own words: to fix what a scan found, to take up the offer of the session note, or to refactor an area. It is no command. Claude loads broom's clean skill for it.

The skill ranks the smells of the repo or an area, agrees a scope and batches with the user, and cleans up worst first. It keeps behavior and the tests green, re-checks each batch and commits it alone.

`broom fixes` gives it the usual fix of each smell, the same line a block message carries. A smell that is deliberate stays, and the skill offers `exclude`, `limits`, `legacy` or `smells_off` instead of contorting the code.

- **Commands**: [broom smells](../CLI.md#broom-smells)
- **Why**: [035: Three commands, and a cleanup that is none](../specs/decisions/035-three-commands.md)
