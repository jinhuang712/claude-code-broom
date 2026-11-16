# F10: Diagnosis

```
F10: Diagnosis
├── F10.1: Whole-repo diagnosis — an old repo's smells in full, as a report and as data
├── F10.2: Hotspots by churn — the files that are both bad and often changed
├── F10.3: Before and after — what a refactor changed, in numbers
├── F10.4: Numbers on request — what a session would otherwise script
└── F10.5: Claude knows what to ask — broom before a script
```

Diagnosis gives a repo its numbers before a refactor and after it. The user ends up with material to plan a refactor from: where the smells are, which files cost most and whether the work paid off.

It measures the whole repo with no time cut, where the checks on a change take 30 seconds at most.

---

## F10.1: Whole-repo diagnosis

One command measures every code file of a repo and gives the result twice: a report a person reads, and data a script or Claude reads.

The report holds the counts by smell and by language, the hotspot files and the worst smells. It names every tool that was missing, since counts without it read as cleaner than the code is.

- **Commands**: [broom smells](../CLI.md#broom-smells)
- **How it works**: [Cleanup](../specs/cleanup.md)

**Stories** (1):

- A user who takes over an old repo runs the diagnosis to see what a refactor would have to deal with.

---

## F10.2: Hotspots by churn

Files are ranked by their smells and by how often they changed in the last 90 days. A bad file that changes every week costs more than a bad file nobody touches, so it comes first.

`/broom:clean` uses this ranking to propose its batches.

---

## F10.3: Before and after

One command compares two revisions and says what the work between them did to the smells: how many went away, how many are new and how each hotspot moved.

- **Commands**: [broom smells](../CLI.md#broom-smells)

---

## F10.4: Numbers on request

One command answers the questions a session would otherwise write a script for, as a table for a person and as data for Claude. It needs no tool installed for the counts that are plain counting.

5 kinds of question:

- **Size**: lines of code by language and by folder, and the longest files, functions and types.
- **Tests**: how many there are, which are skipped, which repeat one another and which code files have none.
- **Rot**: every counter of the check-up, with its value now and at the last check-up.
- **History**: how often each file changed, and which files change together.
- **One file or folder**: all of the above for a path the user names.

A question broom can't answer is said so, with what is missing.

---

## F10.5: Claude knows what to ask

At the start of a session Claude is told in a line which broom command answers a question about the repo, so it asks broom before it writes a script. The line is the end of the limits card. The skills name the command for each kind of question.
