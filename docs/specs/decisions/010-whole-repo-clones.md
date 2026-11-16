# 010. Duplicate code is found across the whole repo with jscpd, and test-to-test clones don't count

Decided: 2026-11-13

---

## The problem

New code that repeats something three directories away is still a duplicate, so this smell needs the whole repo.

---

## The choice

jscpd 5 scans every code file and, given the base ref, that tree too, and marks the clones the base lacked. Clones between two test files are left out.

---

## Not chosen

- **Scan only the changed files**: A copy of code elsewhere in the repo would be missed.
- **Count test-to-test clones**: Sampled over 20 commits in four repos, they were 22 of 27 new clones: setup that tests repeat on purpose.

---

## Consequences

Each distinct change costs one scan of the repo. Clones of generated or vendored code don't count either.
