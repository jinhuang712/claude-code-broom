# 049. What Claude hides is collapsed and still counts

Decided: 2026-11-27

---

## The problem

Claude may hide a finding: accept it with a reason, accept a standing smell the user keeps, or quiet the session note the user said not now to. broom then took it out of the count as well:

- `broom smells`, `broom diagnose` and `broom sweep` gave totals without the known findings, and a later line said how many were hidden.
- The session note vanished after `--dismiss` until the count grew.
- The commit check and the turn's end dropped known issues without a word.

So a total read cleaner than the code was. The user set on 2026-11-27 that whatever an agent hides is only collapsed, and its count never disappears.

---

## The choice

A finding Claude hid leaves the lists and stays in every total, and a line says how many are collapsed:

| Where | Now |
|---|---|
| `broom smells` | `[broom] 51 code smell(s) in <repo>: 0 past the hard limit, 51 hints, 0 nits; 25 accepted as known, collapsed`. JSON gives `known` and `open` beside `total` |
| `broom diagnose` | its summary counts them, and a row says how many are collapsed |
| `broom sweep` | `[broom] N issue(s) in the changed lines; M accepted as known, collapsed` |
| The session note after `--dismiss` | one line with the count and no request for a cleanup, until the count grows |
| The commit check and the turn's end | a check that has something to say adds `broom: N issue(s) accepted as known in the checked files, collapsed`. A check with nothing to say stays silent |

An accepted occurrence counts as one smell, so `open` is the total less what is known.

The session note asks for a cleanup only while a smell past the hard limit is open. One accepted as known is counted and asks for nothing.

---

## Not chosen

- **Hide and say how many in a line of its own**: The total still read cleaner than the code.
- **List the collapsed findings too**: The list is where Claude looks for work, and an accepted finding is no work. `broom known` and `--include-known` list them.
- **A line at every check, silent ones too**: An idle check must cost nothing and say nothing.

---

## Consequences

A repo brought to zero has no open smell, and its total still counts what was accepted. "Zero" means `open` is 0.

The smells part of `broom sweep` never left known smells out, so it lists them and fails on them as before.
