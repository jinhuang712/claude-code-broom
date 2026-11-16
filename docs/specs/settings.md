# Settings

This part resolves what the user and the repo chose. It exists so that one repo can differ from the user's defaults without a question being asked.

A setting resolves in this order: the repo's `.broom.json`, then the plugin's user settings, then the default.

---

## Where the values come from

Hooks receive user settings as environment variables. `broom` run from Bash doesn't get them, so it reads them from Claude Code's settings file.

`.broom.json` sits at the git root. A linked worktree without one reads the main worktree's, so a `.broom.json` that git ignores still reaches the worktrees agents work in. `broom doctor` says where it was read from, and when git ignores it. It flags unknown keys and values.

---

## What the repo's file may hold

`.broom.json` holds only choices and path globs, never commands. Honoring it in an untrusted repo is safe.

`exclude` globs are relative to the root, and `**/x` matches `x` at the root too.
