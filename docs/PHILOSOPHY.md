# Philosophy

Less is more. broom does a few things, quietly, and stays out of the way.

---

## Whose rules decide what is clean?

**The project's tools, not ours.**

broom runs the formatter, linter and type checker a repo already uses, with its configs. Its own defaults only fill a gap where a project has none. It never formats a language the project hasn't set a formatter up for.

---

## Whose bar measures a code smell?

**One bar for smells.**

Code smells are the exception to the project's tools. Long functions, big files, deep nesting and the like are measured against broom's limits in every repo, because how much of them a person will put up with is theirs, not each repo's. They still use each language's own tool to measure.

---

## How much of the code does a check judge?

**Only what changed.**

Lint findings count on the lines that changed, and by default so does formatting. A one-line fix never turns into a reformatted file or a wall of someone else's old warnings. Type errors are the exception: they count anywhere, because a changed signature breaks callers in files nobody touched.

---

## When may a check interrupt?

**Never in the way.**

Checks run at natural checkpoints, not on every edit. Hooks that have nothing to do exit in milliseconds. A missing tool never blocks a commit, and the same lint result never blocks twice. Type errors don't pass on a retry alone: Claude fixes them, or accepts them with a reason that stays on record.

---

## Who decides what is installed or changed?

**Ask, don't assume.**

broom installs nothing and changes no setting without a yes. Hooks can't ask anyone, so they tell Claude, and Claude asks the user. It asks only before acting on the user's machine or repo, never to have them pick settings. Settings start at defaults that suit most people, and the user changes one when they disagree.

---

## What happens to what was skipped?

**Say what happened.**

Every skipped check, timeout and fallback is reported. broom doesn't guess: function boundaries come from a language server or not at all.

---

## Does broom work with other plugins?

**Stand alone.**

broom neither depends on nor integrates with other plugins.
