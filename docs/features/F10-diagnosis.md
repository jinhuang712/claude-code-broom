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

`broom diagnose` measures every code file of a repo, or of the paths given, and gives the result twice: a report a person reads, and with `--json` data a script or Claude reads. `--out FILE` writes it to a file.

The report holds a summary, the smells by kind and by language, the hotspots by churn, the worst smells, the check-up's counters, the tests that repeat one another, the unused dependencies and the four sections of `broom stats`. It names every tool that was missing, since counts without it read as cleaner than the code is. Its last line says how long it took.

It has no time cut and no limit on the number of files. A repo of 5,825 files took 10.4 seconds and one of 18,496 took 49.3, measured on 2026-11-17.

- **Commands**: [broom diagnose](../CLI.md#broom-diagnose)
- **How it works**: [Diagnosis](../specs/diagnosis.md)

**Stories** (1):

- A user who takes over an old repo runs the diagnosis to see what a refactor would have to deal with.

---

## F10.2: Hotspots by churn

Files are ranked by their smells and by how often they changed in the last 90 days. A bad file that changes every week costs more than a bad file nobody touches, so it comes first. Each row shows the file's smells past the hard limit, its hints, its changes and its score.

`broom smells` and `broom diagnose` rank this way, and so do the worst files the session note names. `broom smells --by smells` gives the order by smells alone. With no history the order falls back to that one, and a note says so.

- **Commands**: [broom smells](../CLI.md#broom-smells)
- **How it works**: [Diagnosis](../specs/diagnosis.md)

---

## F10.3: Before and after

`broom compare BASE` measures the repo as it is and as it was at a revision, and says what the work between them did to the smells: per kind the count before and after, the smells that are gone, new, smaller and bigger, and how each hotspot of the base moved. It ends with one line to quote, such as `since v1.2.0: 41 smells -> 12 (-29); past the hard limit 9 -> 0`.

The base is measured in a temporary checkout, which is removed afterwards. A tool that can't run there makes its kinds of smell not comparable, and the report names them.

1 gap:

- A tool that fails in the temporary checkout without saying so is not caught, so its smells read as gone.

- **Commands**: [broom compare](../CLI.md#broom-compare)
- **How it works**: [Diagnosis](../specs/diagnosis.md)

---

## F10.4: Numbers on request

`broom stats` answers the questions a session would otherwise write a script for, as tables for a person and as data for Claude. It needs git and no other tool, and takes a fraction of a second on a small repo.

4 kinds of question:

- **Size**: lines of code by language and by folder with tests counted apart · the longest files.
- **Tests**: the number of test files and test cases · the skipped ones · the code files with no test file by name · what the project's coverage report says.
- **Rot**: the lint suppressions by kind · the TODO comments with how many are older than 180 days · the oldest TODO comments with the day each was written · the skipped tests.
- **History**: the files that changed most in the last 90 days · the pairs of files that changed together.

Paths on the command line narrow all four to a file or a folder. A question it can't answer is said so, with what is missing.

The longest functions and types come from `broom smells --only function_lines` and `--only type_lines`. The list goes on under the soft limit until `--top` is full, and what is under the limit is told as a size and counted as no smell.

3 gaps:

- Rust functions and types under their soft limit are not listed.
- A code file is paired with its test by file name, which misses a test named otherwise.
- Rust and CSS take no part in the pairing.

- **Commands**: [broom stats](../CLI.md#broom-stats)
- **How it works**: [Stats](../specs/stats.md)

---

## F10.5: Claude knows what to ask

At the start of a session Claude is told in a line which broom command answers a question about the repo, so it asks broom before it writes a script. The line is the end of the limits card. `/broom:clean` names the commands for a cleanup: the diagnosis first, the comparison at the end.

- **How it works**: [Setup](../specs/setup.md)
