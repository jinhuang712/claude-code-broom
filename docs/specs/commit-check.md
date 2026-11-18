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

1. The hook sees every Bash call. A shell prefilter leaves unless the input mentions both `git` and `commit`, or the command holds a word a test run could hold, since the same hook notes a test run for the turn's end.
2. `bin/broom` reads the command and leaves unless it could commit.
   - It follows 6 things: `cd` · `git -C` · variables the command sets · `-a` · `--no-verify` · a `git add` in the same command.
   - The body of a heredoc is left out before the command is read, so a message's words are no flags and its apostrophe is no quote.
   - A redirection such as `2>&1` or `> file` is no path of the commit.
3. It works out the files the commit takes. The hook runs before the command, so for `git add . && git commit` it predicts what that add will stage.

A commit with `--no-verify` or `--dry-run` is not checked.

- [002: The commit hook reads every Bash call](decisions/002-every-bash-call.md)

---

## Formatting

The files are formatted, and what was staged in full is staged again. A partly staged file is left alone, so its unstaged hunks can't slip in.

---

## Checking

The files are linted and type-checked, their smells are measured, and the result is filtered to what counts. Findings deny the commit with a report of at most 40 findings, grouped by tool.

The report has a fixed order: what was blocked and what to do, the findings, the usual fix of each kind of smell among them, what is not a fix, the way to accept a finding, and the checks that were skipped. The fix lines come from one data file, which `broom fixes` prints too. The report holds at most 9,000 characters, and findings give way to the rest of it.

A blocked finding passes fixed, or after `broom known --accept "<why>"`, which records the blocked result as known with the reason. Running the same commit again blocks again. `BROOM_NO_ACCEPT` turns accepting off. `broom known --ask` puts the question to the user and passes nothing, so the commit stays denied.

A hint denies the commit as a block does. A note, which is a slight smell, goes into the commit's context without a denial.

- [003: Every finding passes fixed or accepted with a reason](decisions/003-reason-for-every-pass.md)
- [016: A smell past the hard limit blocks like a type error](decisions/016-severe-smells.md)

---

## git's own hook

The PreToolUse hook sees only the command Claude sends. A wrapper that commits holds no `git commit`. `broom install-hook` adds git's pre-commit hook, which runs the same check on whatever commits, a person's included. It checks and doesn't format.

Where it is installed, it is the commit check, and the PreToolUse hook only formats.

git hands its hook `GIT_DIR` in a linked worktree, and a `GIT_WORK_TREE` of `.` under `--work-tree`. With either set, git takes the directory it runs in for the top of the work tree. So the repo is asked of git once, where the hook runs, and never in a file's own folder. In a work tree with no `.git`, jscpd can't read the base, so clones aren't measured there, with a note.

- [004: git's own hook checks without formatting](decisions/004-git-hook-checks.md)

---

## Checked once

Content that passed is recorded by git's blob id for a day. Claude's own commit isn't checked by both hooks, nor again at the turn's end. Only content that passed with no hint, no block and no timeout is recorded, file by file.
