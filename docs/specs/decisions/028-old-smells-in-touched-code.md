# 028. A change is told the old smells in the code it touches

Decided: 2026-11-17

---

## The problem

Only what a change made worse counted. An old smell then stays for good, and one past the hard limit grows a line at a time, each line let through with a reason.

---

## The choice

A change that touches a function or a file with an old smell is told to clean it in the same change, as a hint. Code the change doesn't touch stays quiet.

---

## Not chosen

- **Only what the change made worse**: Old smells are never cleaned unless someone asks for a cleanup.
- **Every old smell in the repo at every change**: A small fix would carry the whole repo's past.

---

## Consequences

A small fix in a bad file now carries a hint about that file. The hint passes with a reason, and the record shows how often it is fixed.
