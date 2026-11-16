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
limit first), `--top` of each, and says how many more there are. Add `--json` to read it as data. With no paths it
covers the repo; with paths, only those.

Pick the scope with the user: an area (`src/layout`), a file, or a kind of smell ("the long functions", "dead
code"). When the request already names it, use that.

## 2. Plan

Propose batches, worst first: one file, or one kind of smell in a few files, per batch. Say for each what changes:
extract functions, split a file, name constants, delete dead code, merge duplicates. Wait for the user's go-ahead
unless they already asked for the cleanup itself.

## 3. Clean one batch

- Keep behavior. Run the project's tests before and after; a failing test stops the batch. If some tests fail
  before you start, note which and compare by name: only a new failure stops a batch.
- Refactor the smell away, not the metric: no splitting a function at an arbitrary line, no `smells_off` to
  silence something fixable.
- A smell that is deliberate (a long lookup table, a protocol's fixed parameter list, code loaded dynamically)
  stays: say so, and offer `.broom.json` `exclude`, `limits` (`test_limits` for tests that are long because they
  list cases), `legacy` (code a migration is replacing) or `smells_off` instead of contorting the code.

How each kind is usually put right:

| Smell | The fix |
|---|---|
| `function_lines`, `complexity`, `nesting` | Extract the steps the function takes into functions named for what they do; return early to flatten |
| `file_lines`, `type_lines` | Split by area, not by size. Move what the parts share into a module of its own first, so they don't import one another |
| `params`, `bool_params` | Group related parameters in one object; make a flag keyword-only (`*, flag` in Python) or an enum |
| `unused_params` | Remove it and the callers' argument. Where a shared signature fixes it (a callback table, a command handler), name it `_name` |
| `magic_numbers` | A named constant that says what the number means, with its unit |
| `nested_ternary` | Plain `if` statements, or early returns |
| `duplicate_lines` | Extract the shared block; where the copies differ, a function with a parameter for the difference |
| `dead_code`, `commented_code` | Delete it; git keeps it |
| `import_cycle` | Move what the files share into a third module both import. An import inside a function is the last resort |
| `folder_cycle` | Decide which folder is the lower layer, and move what it takes from the upper one into a third folder both import, or into the lower one |
| `globals` | Pass the state in, or hold it in an object |
| `debug_output` | Delete it, or use the project's logger |
| `type_escape` | Narrow the type with a check instead of casting or unwrapping |
| `suppression`, `swallowed_error` | Give the suppression its rule and a reason; handle or log the error |
| `todo` | Do it, or write it down as an issue and drop the comment |
| `broad_test_asserts` | Assert on the message or the exact error |

## 4. Check and commit

Run `broom smells` on the same scope again: the batch's smells are gone and nothing new is past a limit. Commit
the batch on its own (broom checks the commit as usual), then go on to the next batch.

## 5. Stop

Stop when the scope is clean, the user says so, or after the batches they agreed to. Report what is left with the
counts from `broom smells`.

If the user doesn't want a cleanup now, run `broom smells --dismiss`: the session note stays quiet until the
repo's count of smells past the hard limit grows.
