# Philosophy

Less is more. broom does a few things, quietly, and stays out of the way.

---

## Who does the thinking?

**Claude thinks, broom doesn't.**

broom holds no model. Every analysis happens in the coding agent that uses it: which smell to clean first, whether a name is good, what to ask about a repo. broom hands that agent what it lacks.

4 things a coding agent lacks:

- **Facts**: It counts a repo another way each time, and broom counts one way.
- **Memory**: Every session starts from nothing, and broom keeps the numbers and the reasons.
- **A gate**: It can talk itself into leaving a finding, and broom can't be talked round.
- **The moment**: It doesn't stop before a commit to check its own work, and broom is there.

---

## Whom does broom serve?

**It helps Claude, and it watches Claude for the user.**

These are two relations, and they run opposite ways. Facts and memory are Claude's to ask for, so there broom is a tool Claude picks up. The gate is the user's hold on Claude, so it doesn't wait to be called: hooks put it into the flow, before each commit and at each turn's end. A feature belongs to one of the two.

---

## Whose rules decide what is clean?

**The project's tools, not ours.**

broom runs the formatter, linter and type checker a repo already uses, with its configs. Its own defaults only fill a gap where a project has none. It never formats a language the project hasn't set a formatter up for.

---

## Whose bar measures a code smell?

**One bar for smells.**

Code smells are the exception to the project's tools. Long functions, big files, deep nesting and the like are measured against broom's limits in every repo, because how much of them a person will put up with is theirs, not each repo's. They still use each language's own tool to measure.

---

## What does broom judge in a test?

**Whether it can lie, not how it reads.**

A test is worth what it proves. A skip, an assertion that any error passes, an error caught and dropped, or a rule silenced lets it pass while the code is wrong, and those stop a change as they do in code. How long a test is, how many parameters it takes and how it is shaped change nothing it proves, so they are told and stop nothing. The project's own tools still judge tests as they judge code.

---

## How much of the code does a check judge?

**Only what changed.**

Lint findings count on the lines that changed, and by default so does formatting. A one-line fix never turns into a reformatted file or a wall of someone else's old warnings. Code a change doesn't touch never comes up. Type errors are the exception: they count anywhere, because a changed signature breaks callers in files nobody touched.

---

## When may a check interrupt?

**At three moments of Claude's flow, each with its own weight.**

After an edit broom formats the file and runs what can be judged in milliseconds, and it only tells. Before a commit it is a gate: what it finds doesn't enter the repo. At a turn's end it settles the account: what Claude was told and left undone comes due, and the turn goes on until it is done. A check that waited for Claude to call it would never run, so hooks put all three into the flow.

Outside these moments broom costs nothing: a hook with nothing to do exits in milliseconds, and a missing tool never blocks.

---

## How does a finding end?

**Fixed, or let through with a reason the user sees.**

There is no third way out. A check that lets Claude carry on after one more try puts Claude's speed before the code, and the user never learns what was left behind. Claude may have a good reason to leave a finding: a refactor that comes in a later step, or a change too large for now. It then tells the user and doesn't keep the reason to itself. What the user agreed to leave, after talking it through, is let through as well. Only what is slight is told and left at that.

Asking the user is no way out for a finding. It ends the turn with the question put, and the finding stays where it is until the user has answered.

---

## What brings back what was held back?

**An event or a count, never the clock.**

No rule of broom turns on how much time passed. Time passing changes no code, so it is no reason to raise a finding again or to stop raising one. What broom holds back, it holds until something happens: a commit, a prompt, a change to the code, a new version of broom. What it trims, it trims by size or by count. Only broom's own running time has a bound, since a hook that hangs holds Claude up, and the bound hides nothing: what a tool cut off would have found is said in a note.

---

## What happens to what Claude hides?

**It is collapsed, and it still counts.**

Claude may hide a finding: accept it with a reason, put it to the user, or quiet a note the user said not now to. That collapses it out of the lists and nothing more. Every total still counts it, and a line says how many are collapsed, so a number never reads cleaner than the code is.

---

## Who decides what is installed or changed?

**Ask, don't assume.**

broom installs nothing and changes no setting without a yes. Hooks can't ask anyone, so they tell Claude, and Claude asks the user. It asks only before acting on the user's machine or repo, never to have them pick settings. Settings start at defaults that suit most people, and the user changes one when they disagree.

---

## What happens to what was skipped?

**Say what happened.**

Every skipped check, timeout and fallback is reported. broom doesn't guess: function boundaries come from a language server or not at all.

---

## When is a smell cleaned?

**Clean as you go.**

A repo doesn't rot in a day. Rot is small smells that were each cheap to fix on the day they appeared, and that nobody fixed. So broom measures a change against the bar while it is being made, when the fix costs a minute. A change also cleans the old smells in the code it touches, since whoever is in that code now knows it best. It keeps a whole-repo scan for the repos that weren't kept this way, and for the day someone plans their refactor.

---

## Does broom work with other plugins?

**Stand alone.**

broom needs no other plugin and asks none to change. It still has to see the edits other tools make, since an edit it can't see is a change nothing checked. So its edit hook knows the edit tools of Serena.
