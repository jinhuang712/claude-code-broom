# 021. A subagent's end checks its own edits

Decided: 2026-11-15

---

## The problem

The main session's turn end checked a subagent's edits, so the session that started it inherited the bill.

---

## The choice

A subagent's edits are recorded under its agent id, and its own end checks them. The block goes to the subagent as its next instruction.

---

## Not chosen

- **Check everything at the main turn's end**: The session that started the subagent inherited the bill.

---

## Consequences

The main session's turn end no longer checks a subagent's edits.
