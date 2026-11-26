# 033. A turn can end with a question to the user, which passes nothing

Decided: 2026-11-18

---

## The problem

A turn's end blocks until a finding is fixed or accepted. But ending the turn is how Claude asks the user anything. A fresh session whose user had to decide whether a finding may be left was blocked three times, each round wasted, before the give-up put the question through.

---

## The choice

`broom known --ask "<question>"` marks what the last block showed as waiting for the user, for that turn only. The turn's end no longer blocks on it and opens the user's line with the question. Nothing passes: the finding stays open and unknown, a commit of it is still denied, and a later turn's end blocks on it again once that turn changes its file.

---

## Not chosen

- **Block until the give-up**: Three rounds are spent to say what one command says, and every question to the user costs them.
- **Let Claude accept and tell afterwards**: The user would learn of it once it is in the repo.

---

## Consequences

A turn can end with a finding open and uncommitted. A user who agrees is asked nothing twice: Claude accepts with `--agreed`, and the summary shows whose call it was.
