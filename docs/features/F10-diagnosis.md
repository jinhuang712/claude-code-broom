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

`broom stats` answers the questions a session would otherwise write a script for, as tables for a person and as data for Claude. It needs git and no other tool, and takes a fraction of a second on a small repo.

4 kinds of question:

- **Size**: lines of code by language and by folder, with tests counted apart, and the longest files.
- **Tests**: how many test files and test cases there are, which are skipped, and which code files have no test file by name.
- **Rot**: the lint suppressions by kind, the TODO comments with how many are older than 180 days, and the skipped tests.
- **History**: the files that changed most in the last 90 days, and the pairs of files that changed together.

Paths on the command line narrow all four to a file or a folder. A question it can't answer is said so, with what is missing.

3 gaps:

- The longest functions and types are not listed. `broom smells` lists those past a limit.
- A code file is paired with its test by file name, which misses a test named otherwise.
- Rust and CSS take no part in the pairing.

- **Commands**: [broom stats](../CLI.md#broom-stats)
- **How it works**: [Stats](../specs/stats.md)

---

## F10.5: Claude knows what to ask

At the start of a session Claude is told in a line which broom command answers a question about the repo, so it asks broom before it writes a script. The line is the end of the limits card. The skills name the command for each kind of question.
