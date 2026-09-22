# Philosophy

Less is more. broom does a few things, quietly, and stays out of the way.

**The project's tools, not ours.**
broom runs the formatter, linter and type checker a repo already uses, with its configs. Its own defaults only
fill a gap where a project has none, and it never formats a language the project hasn't set a formatter up for.

**Only what changed.**
Lint findings count on the lines that changed, and by default so does formatting. A one-line fix never turns
into a reformatted file or a wall of someone else's old warnings. Type errors are the exception: they count
anywhere, because a changed signature breaks callers in files nobody touched.

**Never in the way.**
Checks run at natural checkpoints, not on every edit. Hooks that have nothing to do exit in milliseconds. A missing
tool never blocks a commit, and the same result never blocks twice.

**Ask, don't assume.**
broom installs nothing and changes no setting without a yes. Hooks can't ask anyone, so they tell Claude, and
Claude asks you.

**Say what happened.**
Every skipped check, timeout and fallback is reported. broom doesn't guess: function boundaries come from a
language server or not at all.

**Native, not clever.**
broom is built only from Claude Code's own plugin parts: hooks, skills, settings, `bin/` and `.lsp.json`. No
daemon, and nothing to install beyond Python 3.9 and the tools themselves.

**Stand alone.**
broom neither depends on nor integrates with other plugins.
