# Stats

This part counts what a session would otherwise write a throwaway script to count. It exists so that two sessions asked the same question about a repo give the same answer.

```
the repo's code files ──▶ one pass over each file's text ──▶ size · tests · rot
git log, once ───────────────────────────────────────────▶ history
git blame, on the lines that hold a TODO ────────────────▶ the age of each TODO
```

---

## Which files

It reads the files every other part of broom reads: tracked and untracked code files, with dependencies, build output, generated code and the paths `.broom.json` excludes left out. Paths on the command line narrow it.

It needs git and nothing else. No linter runs.

---

## One pass over the text

A small scanner follows strings and block comments across lines, so a marker inside a string is told from one in a comment. For each file it gives the non-blank lines, the test cases and skipped tests by each language's own form, the lint suppressions and the TODO comments.

Test cases and skipped tests are read in test files only, except in Rust, where tests sit beside the code. A conditional skip, such as a test that skips when a tool is missing, counts as skipped.

A code file is paired with a test file by name, anywhere in the repo. Rust and CSS take no part in the pairing.

---

## History

One `git log` over the period gives the commits per file and the pairs of files that changed in the same commit. A commit of more than 30 files is left out of the pairs, since it says nothing about which two files belong together.

---

## The age of a TODO

`git blame` runs only on the files that hold a TODO comment, on 200 such lines at most, the files with most first. When the cap is hit, the output says so. An untracked file is not blamed.
