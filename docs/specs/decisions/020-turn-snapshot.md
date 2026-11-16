# 020. The turn's changes come from a snapshot at the prompt, not only from edit records

Decided: 2026-11-15

---

## The problem

A Bash command can rewrite files with sed, a codemod or `git mv`. A wrapper that commits holds no `git commit` for the commit hook. In one repo that was the main way changes landed, and nothing checked it.

---

## The choice

An async prompt hook notes the changed code files by modification time and size, and HEAD. The turn's end adds what changed and what was committed since.

---

## Not chosen

- **Only the files Edit and Write touched**: Everything Bash changed went unchecked.

---

## Consequences

The snapshot costs about 0.2 seconds on a 2,376-file repo at each prompt, which no prompt waits for.
