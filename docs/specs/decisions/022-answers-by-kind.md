# 022. Setup answers are remembered by kind of gap for every repo

Decided: 2026-09-26

---

## The problem

A gap the user left alone in one repo was raised again in the next.

---

## The choice

A setup answer stores each gap's kind in a user-wide list: language, role, tool and status, with no path. A repo is raised only when it has a gap of a kind not in that list.

---

## Not chosen

- **Remember answers per repo**: Machine-wide tools and user settings are shared anyway, so the same question came back.

---

## Consequences

A new repo only asks about kinds of gap the user hasn't answered yet. `broom setup --reset` forgets them all.
