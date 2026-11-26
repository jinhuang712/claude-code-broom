# 047. A standing smell is accepted with the user's agreement

Decided: 2026-11-27

---

## The problem

`broom known --accept` accepts only what the last blocked commit or turn's end showed. A smell in code nobody touches never blocks, so it could never be accepted, and `broom smells` listed it for good, even when the user had decided it stays.

A repo brought to zero smells shows the cases: a rounding such as `(ms+999)/1000`, the constants of a published formula, a guard that recovers on purpose, a boolean a function type fixes, a block two modules repeat because neither may import the other.

---

## The choice

One flag on `broom known`, writing the record an accepted block writes:

```
broom known --accept "<why>" --agreed --smell KIND FILE[:LINE]...
```

| Part | Means |
|---|---|
| `--smell KIND` | the kind of smell, as `broom smells` names it |
| `FILE:LINE` | the smell on that line, as `broom smells` lists it |
| `FILE` or a folder | every smell of that kind in it |
| `--agreed` | required: a standing smell is accepted only once the user agreed |

Each occurrence is an entry of its own, so a file with 3 magic numbers keeps 2 after one is accepted. An entry is keyed by:

| Smell | Key | Comes back when |
|---|---|---|
| an occurrence | its file, its kind and the text of its line | that line changes |
| a sized smell | its file, its kind, its message and the text of its first line | its size, its name or its first line changes |

A duplicate block's message names the other side's line, so it also comes back when lines above the other side move.

`broom smells` and `broom diagnose` leave a known smell out and say how many they left out. So does the session note's count of smells past the hard limit.

---

## Not chosen

- **A second store for standing smells**: The known-issue store holds the same thing: a finding, a reason and whether the user agreed.
- **`--agreed FILE:LINE`**: It turns a flag that says who agreed into one that names places, and the paths `broom known` already takes do that.
- **An accept without the kind**: One line can hold two smells, and the user agrees to one.
- **Claude accepting on its own**: A block offers an accept because the work must go on. Nothing waits on a standing smell, so only the user's decision leaves it.
- **A ledger line**: Nothing blocked the smell, so a pass would count against a rule's fix rate.
- **The hooks reading these entries**: A standing smell reaches a hook only once its code changed, and then it should come back.

---

## Consequences

Two occurrences of one kind on lines with the same text in one file share a key, so accepting one accepts both.

2 gaps:

- The session note reads a scan cached by HEAD, so an accept shows there after the next commit.
- An accept writes no line to the record, so `broom report` doesn't show it. `broom known` lists it with its reason.
