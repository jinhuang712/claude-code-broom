# 043. A question that nothing ended counts against its rule

Decided: 2026-11-26

---

## The problem

The fix rate was the fixed over the fixed plus the let through, so a finding still open counted against no rule. A finding put to the user with `--ask` stays open until a later check finds it gone or it is accepted, and most of them had neither.

So a rule that was mostly noise read as fixed every time. On 2026-11-26 three Go rules read 100%: `type_escape` had 6 of 44 findings fixed and 36 open after a question, and `globals` and `bool_params` were alike. They were noise, found by hand that day. [M1: Fix rate](../../plan/GOALS.md#m1-fix-rate) is there to find exactly that.

---

## The choice

An open finding the user was asked about counts against its rule's fix rate: the code still holds it. When a later check finds it gone, it is fixed, and when it is accepted, it is let through, as before.

It stays open in the report and is never shown as let through, so no problem reads as settled. The report gives the open findings with how many of them were asked about, as in `38 (asked 36)`.

A finding still open that nobody asked about counts against no rule, as before. On 2026-11-26 the ledger held 89 of them.

---

## Not chosen

- **Leave them out, as before**: A rule nobody fixes reads as always fixed.
- **Count them as let through**: The user's want is that no problem is hidden. A finding shown as let through reads as settled while the code still holds it.
- **Close them when the user answers**: The answer is the next prompt's free text, and broom holds no model to read it.

---

## Consequences

The fix rate of the ledger of 2026-11-26 reads 51% where it read 81%.

A question the user is still thinking about counts against its rule until a check finds the finding gone. The rate covers 30 days, so a fresh question weighs little.

The ledger is unchanged: an `ask` line is still no outcome, and the gate is unchanged too.
