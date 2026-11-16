# 004. git's own hook checks without formatting, and is the commit check where it is installed

Decided: 2026-11-16

---

## The problem

The PreToolUse hook sees only the command Claude sends. A wrapper that commits for the user holds no `git commit`, so in one repo the main path of committing was never checked. And the hook runs before the command, so it can only guess from the arguments which files the commit will take.

---

## The choice

`broom install-hook` adds git's pre-commit hook, which runs the same check on the staged files of whatever commits. It doesn't format. Where it is installed, the PreToolUse hook only formats.

---

## Not chosen

- **Format in git's hook too**: Rewriting files under a person's commit is theirs to choose.
- **Both hooks check**: The same content would be checked twice, and the guess could disagree with the staged files.

---

## Consequences

The hook is installed by hand, one repo at a time. It never replaces another tool's hook and prints the line to add to it instead.
