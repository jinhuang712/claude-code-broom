# 046. A known issue never expires

Decided: 2026-11-27

---

## The problem

A known issue expired after 30 days. The limit came with the known-issue list in 0.3.0 as a constant in the code, and no decision ever chose it. The docs later described it as a debt raised again after a month.

The user never asked for a rule in time. A finding accepted with a reason came back with its code unchanged, so the same reason had to be given again.

It didn't even hold as written: the entries older than 30 days were dropped only when the next accept was written, so an old one hid its finding until then.

---

## The choice

A known issue stays known until its code changes or `broom known --clear` removes it.

Its key already holds the text of its line, the tool, the rule and the message. A change to that line, or a sized smell that grew, makes a new key, and the finding comes back.

---

## Not chosen

- **Expiry after a time**: It brings back code nobody changed, and the time chosen is no one's decision.
- **Dropping an entry whose line is gone**: An entry accepted in a linked worktree names the main checkout's file, which holds the line only after the work lands. A drop before that would lose it.

---

## Consequences

An entry whose code changed hides nothing and stays in the store, listed by `broom known`, until `broom known --clear` removes it.

The store grows with every accept and shrinks only by `--clear`.
