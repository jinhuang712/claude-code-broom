# Diagnosis

This part measures a whole repo for someone who plans a refactor, and measures two revisions to say what the work between them did. It exists because a refactor that starts without numbers can't say where to begin or whether it paid off.

```
broom diagnose ─▶ every code file ─┬─▶ smells, with no base and no time cut ─┐
                                   └─▶ stats: size · tests · rot · history ──┼─▶ one report, as text and as JSON
git log, once ─▶ commits per file ─▶ hotspots by churn ──────────────────────┘

broom compare BASE ─▶ measure the repo now ───────────────┐
                  └─▶ check BASE out in a temporary tree ─┼─▶ match ─▶ gone · new · smaller · bigger
                      measure it there, then remove it ───┘
```

---

## Hotspots by churn

A hotspot's score is its smells times one more than the commits that touched it in the last 90 days, with a smell past the hard limit counted three times:

```
score = (3 x past the hard limit + hints) x (1 + changes)
```

The commits per file come from one `git log`. When no commit falls in the period, or git log fails, every file has no changes and the order is by smells alone, with a note that says so.

---

## The whole-repo report

The report composes what the other parts measure. The smells are found with no base, so nothing in it is new, and with no time budget, so the limit of the session scan doesn't apply. The stats are those of `broom stats`.

It names every tool that was missing, since counts without a tool read as cleaner than the code is. Its last line says how long it took.

---

## Two revisions

The base revision is checked out into a temporary linked worktree in the system's temp directory, measured there and removed, also when something fails. The entry git keeps for it and the measurement rows cached for its path are removed too. Stale worktree entries are pruned only when the removal failed, since pruning drops every worktree whose directory is gone.

Smells match across the two measurings by file, smell and the function's name, else the text of the line. A file git sees as renamed is matched to its old path.

A tool that can't run in the temporary tree, as when its dependencies are installed only in the working tree, leaves a note on one side only. The smells of that tool are then left out of every count and list, and the report names the kinds that are not comparable. A tool that fails there without a note is not caught.

The caches golangci-lint and clippy make for the temporary path stay until the usual 7-day prune removes them.
