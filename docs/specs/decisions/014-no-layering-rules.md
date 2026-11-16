# 014. broom adds no layering rules without a project's own

Decided: 2026-11-13

---

## The problem

Tools such as depguard and dependency-cruiser can hold imports to declared layers. They run only with rules a project wrote.

---

## The choice

broom doesn't add layering rules. It reports cycles between modules and between folders, which need no rules.

---

## Not chosen

- **Ship default layer rules**: None of the author's repos has any, and layers differ per project.

---

## Consequences

A layer that imports upward without closing a cycle is not seen.
