# What counts

This part decides which of a tool's findings reach Claude. It exists so that a legacy repo's old findings never land on a small change.

---

## Changed lines

A lint finding counts on a line that differs from the base, read from `git diff -U0`. An untracked file counts whole. A compile or type error counts anywhere, including files nobody touched.

A file git sees as renamed is compared with its old path, so a move changes no line.

Files the repo's `.broom.json` excludes never count. Files outside any git repo are no project's code, and the hooks neither record nor format them.

---

## Known issues

A finding Claude accepted with a reason is recorded as known and not raised again. Its key is the file, the tool, the rule, the message and the text of the line, so it stays known when lines above it move. The file is named by its path from the repo's root, and known issues live in the main checkout's `.broom/`, so a finding accepted in a linked worktree stays known once the work lands, and a repo moved to another folder keeps them.

A known issue never expires. It stays known until its code changes, which makes a new key, or until `broom known --clear` removes it. `broom known` lists them, with the reason beside each accepted one and whether the user agreed. An entry that no line of its file gives any more, in the main checkout or in a linked worktree, is marked as one whose code changed. It hides nothing, and it stays until `broom known --prune` drops it with the others whose code changed, or until `--clear`.

A smell that stands in code no change touches never blocks, so it is accepted another way: by its kind and its place, with the user's agreement, as `broom known --accept WHY --agreed --smell KIND FILE[:LINE]`. Each occurrence is keyed by its file, its kind and the text of its line. A sized smell is keyed by its message, which holds its name, its size and its limit, and by the text of its first line. `broom smells`, `broom diagnose` and the session note collapse a known one: no list shows it, every total counts it, and the first line says how many are collapsed. A check that has something to say adds one line with how many known issues in its files it collapsed, and a check with nothing to say stays silent. The hooks don't read these entries, since a standing smell reaches a hook only once its code changed.

- [003: Every finding passes fixed or accepted with a reason](decisions/003-reason-for-every-pass.md)
- [046: A known issue never expires](decisions/046-known-issues-never-expire.md)
- [047: A standing smell is accepted with the user's agreement](decisions/047-standing-smells-accepted.md)
- [053: What broom finds in a repo lives in the repo's `.broom/`](decisions/053-findings-live-in-the-repo.md)

---

## Notes

A missing tool, a timeout and a fallback each make a note. A note is shown once per session, so a missing tool is mentioned once and not at every check.
