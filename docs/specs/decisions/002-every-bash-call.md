# 002. The commit hook reads every Bash call instead of matching `if` patterns

Decided: 2026-09-23

---

## The problem

Claude Code's `if` patterns such as `Bash(git commit *)` never matched commands such as `T=~/repo; git -C $T commit` or `git -c key=val commit`. Those committed unchecked.

---

## The choice

The hook sees every Bash call. A shell prefilter leaves unless the input mentions both `git` and `commit`, and a parser then follows the command.

---

## Not chosen

- **More `if` patterns**: A pattern can't follow a variable the command sets.

---

## Consequences

Every Bash call pays a shell start, about 13 ms. broom carries a parser for shell commands, and for `git add . && git commit` it can only predict what the add will stage.
