# 053. What broom finds in a repo lives in the repo's `.broom/`

Decided: 2026-11-27

---

## The problem

Everything broom found in every repo sat in one data directory of the machine, keyed by absolute paths: the known issues, the ledger, the last blocked result and the check-up's counters. 3 things followed:

- A repo moved to another folder lost its known issues and its record, since no path matched any more.
- A repo deleted left its records in the data directory for good.
- A linked worktree needed its paths mapped to the main checkout, and an entry from a worktree since deleted read as changed code. The data directory held 250 such known issues on 2026-11-27.

The user set that day that what broom finds in a repo is bound to the repo, and that it is never committed.

---

## The choice

What broom finds in a repo lives in a `.broom/` folder at the root of the repo's main checkout. Every linked worktree reads and writes that one folder.

| Where | What |
|---|---|
| `<repo>/.broom/` | known issues · the repo's ledger · the last blocked result · the check-up's counters · the session scan and its dismissed note · content that passed · a check that ran out of time |
| the data directory | the tools' caches · sessions and claims · setup answers · the doctor's cache · the hook trace · an index of the repos that have a `.broom/` |

A file in `.broom/` names a file of the repo by its path from the repo's root, so a moved repo keeps what it had.

`.broom/` holds a `.gitignore` of `*`, so git ignores it without a change to the repo's own `.gitignore`. The repo's config, `.broom.json`, is committed and stays where it is.

A `.broom/` that git tracks came with the repo, and broom never reads it: a repo could ship known issues that hide its findings. broom then keeps that repo's records in a folder of the data directory and says so in a note, as it does for a repo whose root it can't write.

The first time broom makes a repo's `.broom/`, it moves that repo's records out of the data directory's files.

---

## Not chosen

- **Committed with the repo**: Every accept would leave a change to commit, and a repo from anyone could bring known issues that hide its findings.
- **The repo's `.git/broom/`**: It is bound to the repo too, but the user picked a folder they can see.
- **The data directory, keyed per repo**: A moved repo still loses its records, and a deleted one still leaves them.

---

## Consequences

`broom report --all` finds each repo through the index, so a repo deleted drops out of it.

A repo's records go with its folder: a copy of the folder carries them, and deleting the folder deletes them.

The paths of linked worktrees no longer need mapping for known issues, since every worktree writes the main checkout's folder by paths from the root.
