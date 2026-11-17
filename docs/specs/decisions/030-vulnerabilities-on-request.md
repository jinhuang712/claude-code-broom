# 030. Known vulnerabilities are looked up only on request

Decided: 2026-11-17

---

## The problem

Looking up known vulnerabilities sends the names and versions of a repo's packages to a public database. Every other check broom runs stays on the machine.

---

## The choice

Only `broom diagnose --vulnerabilities` starts osv-scanner. The report says what is sent and where, before the result.

---

## Not chosen

- **Part of every diagnosis**: A user who runs a diagnosis on a private repo would send its package list without being told.
- **A setting that turns it on for good**: It would also run where the user didn't think of it, and one flag costs nothing to type.
- **A counter of the check-up**: The check-up runs at session start, with no one there to agree.

---

## Consequences

The check-up never tells of a new vulnerability. A user who wants that runs the diagnosis with the flag, or keeps the scan in CI.
