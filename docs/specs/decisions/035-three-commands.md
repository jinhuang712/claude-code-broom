# 035. Three commands, and a cleanup that is none

Decided: 2026-11-19

---

## The problem

broom had 4 commands, and they overlapped. `/broom:status` set up a repo as `/broom:setup` does and measured it as a scan would. `/broom:sweep` checked what the hooks had already checked. `/broom:sweep` and `/broom:clean` both answered a request to clean up.

---

## The choice

3 commands, each with its own question:

| Command | Answers | Changes something |
|---|---|---|
| `/broom:setup` | what does broom need here | yes, after asking |
| `/broom:status` | how does broom stand here | only a setup the user agrees to |
| `/broom:scan` | how is the code | no |

Status is about broom and runs no linter. Scan is about the code, finds and fixes nothing. A cleanup is no command: the user asks in their own words, and Claude loads the clean skill.

---

## Not chosen

- **Status as an overview of the repo**: It measured the code as a scan does, so nobody could say which of the two to run.
- **No status**: What broom let through, and why, would have no command.
- **Keep `/broom:sweep`**: The hooks format and check Claude's work, and a scan with a scope covers what no hook saw.
- **Keep `/broom:clean` as a command**: A scan ends with an offer to fix, and a fourth command to accept it is one more name to learn.
- **Drop the clean skill**: Its way of cleaning would be lost: worst first, in small batches, each one checked.

---

## Consequences

A user who wants a scope formatted asks Claude, or runs `broom sweep`. Status keeps its offer to set up on one yes, which hands over to the setup's own steps.
