# 015. Tools that need types or a module graph run in the project's checkout

Decided: 2026-11-15

---

## The problem

The scratch copy holds the changed files and not their packages, so imports don't resolve. One linter that needs types makes golangci-lint skip every linter in the run.

---

## The choice

Go's typed linters, import cycles and clippy run in the real tree. A finding counts when it is on a line the change added.

---

## Not chosen

- **Copy whole packages into the scratch copy**: Dependencies would have to resolve there too.

---

## Consequences

There is no base to compare with, so a finding the change moved onto a new line counts as added. A crate is checked whole.
