# 041. A commit counts as the turn's when it was made after the prompt

Decided: 2026-11-26

---

## The problem

The turn's end counted every commit between the prompt's HEAD and its own. A turn that pulled a remote's commits got every finding in them as its own. On the author's machine one such turn was blocked for code it never wrote, and its questions to the user about that code filled the ledger.

---

## The choice

A commit counts when git's committer time is no earlier than the second the prompt noted the tree. The turn's change is measured from the newest older commit on HEAD's first-parent line, or from the prompt's HEAD when there is none.

---

## Not chosen

- **Every commit since the prompt's HEAD**: A pull made the turn own a remote's code.
- **Leave out the commits a remote branch holds**: A turn that pushes its own commits would lose them, and work landed from a local worktree is on no remote.
- **The reflog's verbs**: A session that lands its own worktree by a fast-forward reads like a pull.

---

## Consequences

- Another session's commit made in the same checkout during the turn still counts as the turn's.
- A remote commit made after the prompt and then pulled counts too.
- Commits a turn lands from work done before its prompt are not checked again at its end, since their own commits and turns checked them.
- A turn's end with code to check makes one more git call.
