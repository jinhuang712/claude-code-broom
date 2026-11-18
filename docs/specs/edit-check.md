# Edit check

This part formats a file and tells Claude what a fast linter finds, right after an edit. It exists so that Claude hears of a finding while the edit is fresh, at a cost an edit doesn't feel.

```
edit ─▶ format, where the project formats ─▶ the fast linter of the language ─▶ on a line that differs from HEAD?
                                                                                   │ yes, and not told before
                                                                                   ▼
                                                                         one line of context for Claude
```

---

## What runs

Only what judges one file in tens of milliseconds runs here: ruff · oxlint without its type-aware rules · SwiftLint. Each tool gets two seconds at most, the formatter too. A tool that is missing, slow or failing says nothing.

What needs a build, a Node start with a project's own plugins or the whole repo waits for the commit: clippy · golangci-lint · tsc · swift build · ESLint · stylelint · jscpd.

- [032: After an edit broom formats and runs what is judged in milliseconds](decisions/032-light-check-after-an-edit.md)

---

## What is told

A finding counts as it does at a commit: on a line that differs from HEAD, and not known. It is told once for a file in a session, and again only after it went away and came back. A message names five findings at most and counts the rest. The hook never blocks.

---

## Switches

`check_on` at `off` turns the check off. `format_on` at `commit` or `off` turns the format after an edit off. An edit of a file with no language, outside a repo or excluded by `.broom.json` costs what it did before.
