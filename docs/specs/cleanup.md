# Cleanup

This part ranks the smells already in a repo and tells Claude when there are severe ones. It exists because hooks gate what a change makes worse, and the smells already there need someone to go after them.

---

## Ranking

`broom smells` measures the repo or some paths with no base, so nothing in it is "new". It ranks the hotspot files by their smells and by how often they changed, and the worst smells, furthest past their limit first.

With `--base REV` it lists only what the changes since that revision made worse, with each smell's size or count at the revision.

A smell the known-issue store holds is collapsed: the hotspots and the worst smells leave it out, the counts keep it, and the first line says how many are collapsed. `broom diagnose` and the session note count it the same way.

Asked for function or type lengths alone, it measures a second time with that soft limit at 1, so the tools report every function or type. The rows under the real limit fill what `--top` leaves after the smells. The measurement cache keeps rows by the limits they were measured under, so these never reach a check.

- [047: A standing smell is accepted with the user's agreement](decisions/047-standing-smells-accepted.md)

---

## The session scan

The repo is scanned once per commit, cached by HEAD. The scan runs in an async hook when no scan of HEAD is cached, and its note reaches Claude with its next turn. The session hook says only what a cached scan knows.

On a 2,376-file repo the scan took 13 to 36 seconds. On a 3,184-file repo it took 20.7 seconds cold and 4.0 warm. A repo of more than 5,000 files is not scanned at session start.

- [017: The session scan runs in an async hook](decisions/017-async-session-scan.md)

---

## The note

When smells past the hard limit exist, Claude is told to raise them at a natural point and offer a cleanup. It doesn't start a cleanup.

`broom smells --dismiss` records the count of severe smells. The note then gives only that count, in one line, and asks for no cleanup, until the count grows. The count holds the smells accepted as known, collapsed.

- [018: broom offers a cleanup and never starts one](decisions/018-offer-cleanup.md)
