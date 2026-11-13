---
name: clean
description: Clean up the code smells broom finds across a repo or an area - long functions, files and types, high complexity, deep nesting, duplicate and dead code, magic numbers and the like - worst first, in small verified batches. Use for /broom:clean, when broom's session note reports smells and the user agrees to a cleanup, when the user asks to clean up, refactor or pay down tech debt, or before reworking an area that `broom smells` ranks as a hotspot.
argument-hint: "[area or kind of smell, in your words]"
---

## 1. Rank

```bash
broom smells [paths] --top 10
```

It lists the hotspot files (most smells past the hard limit first) and the worst smells (furthest past their
limit first). Add `--json` to read it as data. With no paths it covers the repo; with paths, only those.

Pick the scope with the user: an area (`src/layout`), a file, or a kind of smell ("the long functions", "dead
code"). When the request already names it, use that.

## 2. Plan

Propose batches, worst first: one file, or one kind of smell in a few files, per batch. Say for each what changes:
extract functions, split a file, name constants, delete dead code, merge duplicates. Wait for the user's go-ahead
unless they already asked for the cleanup itself.

## 3. Clean one batch

- Keep behavior. Run the project's tests before and after; a failing test stops the batch.
- Refactor the smell away, not the metric: no splitting a function at an arbitrary line, no `smells_off` to
  silence something fixable.
- A smell that is deliberate (a long lookup table, a protocol's fixed parameter list, code loaded dynamically)
  stays: say so, and offer `.broom.json` `exclude`, `limits` or `smells_off` instead of contorting the code.

## 4. Check and commit

Run `broom smells` on the same scope again: the batch's smells are gone and nothing new is past a limit. Commit
the batch on its own (broom checks the commit as usual), then go on to the next batch.

## 5. Stop

Stop when the scope is clean, the user says so, or after the batches they agreed to. Report what is left with the
counts from `broom smells`.

If the user doesn't want a cleanup now, run `broom smells --dismiss`: the session note stays quiet until the
repo's count of smells past the hard limit grows.
