# What counts

This part decides which of a tool's findings reach Claude. It exists so that a legacy repo's old findings never land on a small change.

---

## Changed lines

A lint finding counts on a line that differs from the base, read from `git diff -U0`. An untracked file counts whole. A compile or type error counts anywhere, including files nobody touched.

A file git sees as renamed is compared with its old path, so a move changes no line.

Files the repo's `.broom.json` excludes never count. Files outside any git repo are no project's code, and the hooks neither record nor format them.

---

## Known issues

A finding Claude accepted with a reason is recorded as known and not raised again. Its key is the file, the tool, the rule, the message and the text of the line, so it stays known when lines above it move. The file is named as the main checkout holds it, so a finding accepted in a linked worktree stays known once the work lands.

A known issue expires after 30 days. `broom known` lists and clears them, with the reason beside each accepted one.

- [003: Every finding passes fixed or accepted with a reason](decisions/003-reason-for-every-pass.md)

---

## Notes

A missing tool, a timeout and a fallback each make a note. A note is shown once per session, so a missing tool is mentioned once and not at every check.
