# Cleanup

This part ranks the smells already in a repo and tells Claude when there are severe ones. It exists because hooks gate what a change makes worse, and the smells already there need someone to go after them.

---

## Ranking

`broom smells` measures the repo or some paths with no base, so nothing in it is "new". It ranks the hotspot files, most smells past the hard limit first, and the worst smells, furthest past their limit first.

With `--base REV` it lists only what the changes since that revision made worse, with each smell's size or count at the revision.

---

## The session scan

The repo is scanned once per commit, cached by HEAD. The scan runs in an async hook when no scan of HEAD is cached, and its note reaches Claude with its next turn. The session hook says only what a cached scan knows.

On a 2,376-file repo the scan took 13 to 36 seconds. On a 3,184-file repo it took 20.7 seconds cold and 4.0 warm. A repo of more than 5,000 files is not scanned at session start.

- [017: The session scan runs in an async hook](decisions/017-async-session-scan.md)

---

## The note

When smells past the hard limit exist, Claude is told to raise them at a natural point and offer `/broom:clean`. It doesn't start a cleanup.

`broom smells --dismiss` records the count of severe smells. The note returns only when that count grows.

- [018: broom offers a cleanup and never starts one](decisions/018-offer-cleanup.md)
