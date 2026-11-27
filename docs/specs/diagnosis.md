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

A hotspot's score is its smells times one more than the commits that touched it in the last 500 commits, with a smell past the hard limit counted three times:

```
score = (3 x past the hard limit + hints) x (1 + changes)
```

A nit weighs nothing, so a file that holds nits alone is left out of the hotspots and stays in the list of smells.

The commits per file come from one `git log`. When no commit falls in the period, or git log fails, every file has no changes and the order is by smells alone, with a note that says so.

---

## The whole-repo report

The report composes what the other parts measure. The smells are found with no base, so nothing in it is new, and with no time budget, so the limit of the session scan doesn't apply. The stats are those of `broom stats`.

It names every tool that was missing, since counts without a tool read as cleaner than the code is. Its last line says how long it took.

---

## Dependencies

The unused packages come from each language's own tool, run once per project directory the doctor's scan found. knip reads a whole JS workspace from its root and cargo-machete every crate under a directory, so a project below such a root is left to the run there. Go needs no install: `go mod tidy -diff` prints what it would drop from `go.mod`, and it runs with the proxy off, so it reads the module cache and no network.

Each tool gets five minutes. One that isn't installed is named once with its install command. One that fails is shown with its first error line, so a tool's failure never reads as "none unused".

Known vulnerabilities come from osv-scanner, which sends the names and versions of the packages in the lockfiles to a public database. Nothing starts it but the `--vulnerabilities` flag. A lockfile it gives in several results is one row. A fix that the database names by a commit is left out, since it is no version.

- [029: A tool broom can do without is listed and never asked for](decisions/029-optional-tools.md)
- [030: Known vulnerabilities are looked up only on request](decisions/030-vulnerabilities-on-request.md)

---

## Two revisions

The base revision is checked out into a temporary linked worktree in the system's temp directory, measured there and removed, also when something fails. The entry git keeps for it and the measurement rows cached for its path are removed too. Stale worktree entries are pruned only when the removal failed, since pruning drops every worktree whose directory is gone.

Smells match across the two measurings by file, smell and the function's name, else the text of the line. A file git sees as renamed is matched to its old path.

A tool that can't run in the temporary tree, as when its dependencies are installed only in the working tree, leaves a note on one side only. The smells of that tool are then left out of every count and list, and the report names the kinds that are not comparable. A tool that fails there without a note is not caught.

The caches golangci-lint and clippy make for the temporary path stay until their count bound trims them: the newest 20 golangci-lint caches and 10 clippy build folders are kept.
