# 009. An occurrence smell counts when the change raises the count in a file

Decided: 2026-11-13

---

## The problem

Smells that count by occurrence can't use limits: one more magic number in a file of 225 is the signal.

---

## The choice

An occurrence counts when the change raises the count in a file, matched by the text of the line so moved code stays old.

---

## Not chosen

- **Count edited lines too**: Count-neutral edits then hinted, which sampling the author's repos showed as noise.

---

## Consequences

An edit that swaps one occurrence for another of the same text is not seen.
