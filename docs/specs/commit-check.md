# Commit check

The commit check formats what a `git commit` takes, lints and type-checks it, and denies the commit while findings remain. It exists so that Claude's work meets the project's rules before it lands.

It has two entrances. Claude Code's PreToolUse hook sees the Bash command before it runs. git's own pre-commit hook, once `broom install-hook` adds it, sees the staged files.

```
Bash call ─▶ hooks/commit.sh ─▶ mentions git and commit? ─ no ─▶ exit (~13 ms)
                                        │ yes
                                        ▼
                               bin/broom reads the command ─ can't commit ─▶ exit (~60 ms)
                                        │ a commit
                                        ▼
                               the files it takes ─▶ format · re-stage ─▶ check ─▶ deny, or let through
```

---

## Reading the command

1. The hook sees every Bash call. A shell prefilter leaves unless the input mentions both `git` and `commit`.
2. `bin/broom` reads the command and leaves unless it could commit. It follows `cd`, `git -C`, variables the command sets, `-a`, `--no-verify`, a `git add` in the same command, and flags inside a heredoc message that must not count.
3. It works out the files the commit takes. The hook runs before the command, so for `git add . && git commit` it predicts what that add will stage.

A commit with `--no-verify` or `--dry-run` is not checked.

- [002: The commit hook reads every Bash call](decisions/002-every-bash-call.md)

---

## Formatting

The files are formatted, and what was staged in full is staged again. A partly staged file is left alone, so its unstaged hunks can't slip in.

---

## Checking

The files are linted and type-checked, their smells are measured, and the result is filtered to what counts. Findings deny the commit with a report of at most 40 lines, grouped by tool.

Committing the same lint result again passes and records the findings as known. After three denials a lint result passes too. A type error or a severe smell doesn't pass on a retry: it passes fixed, or after `broom known --accept "<why>"`, which records the blocked result as known with the reason. `BROOM_NO_ACCEPT` turns accepting off.

A hint goes into the commit's context without a denial.

- [003: A lint result passes on a retry and a type error doesn't](decisions/003-retry-and-accept.md)
- [016: A smell past the hard limit blocks like a type error](decisions/016-severe-smells.md)

---

## git's own hook

The PreToolUse hook sees only the command Claude sends. A wrapper that commits holds no `git commit`. `broom install-hook` adds git's pre-commit hook, which runs the same check on whatever commits, a person's included. It checks and doesn't format.

Where it is installed, it is the commit check, and the PreToolUse hook only formats.

- [004: git's own hook checks without formatting](decisions/004-git-hook-checks.md)

---

## Checked once

Content that passed is recorded by git's blob id for a day. Claude's own commit isn't checked by both hooks, nor again at the turn's end. Only content that passed with no hint, no block and no timeout is recorded, file by file.
