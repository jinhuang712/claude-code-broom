# F10: Diagnosis

```
F10: Diagnosis
├── F10.1: Whole-repo diagnosis — an old repo's smells in full, as a report and as data
├── F10.2: Hotspots by churn — the files that are both bad and often changed
└── F10.3: Before and after — what a refactor changed, in numbers
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
