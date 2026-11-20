# 013. Dead code counts only on lines the change added

Decided: 2026-11-13

---

## The problem

Code nothing uses is something Claude wrote and never wired in. A whole-repo list of it in a legacy repo would be noise.

---

## The choice

A dead-code finding counts on a line the change added, or in a new file. It is a nit, told without a block, since what loads dynamically looks unused too.

---

## Not chosen

- **Go's `deadcode`**: It sees only programs with a `main`.
- **Swift's periphery**: It needs a full build, too slow for a hook.
- **Count unused code anywhere**: It would raise legacy code a change left as it was.

---

## Consequences

An export that a change left unused elsewhere is missed. What loads dynamically looks unused too, so `smells_off` turns it off per repo.
