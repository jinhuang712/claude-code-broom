# Stats

This part counts what a session would otherwise write a throwaway script to count. It exists so that two sessions asked the same question about a repo give the same answer.

```
the repo's code files ──▶ one pass over each file's text ──▶ size · tests · rot
git log, once ───────────────────────────────────────────▶ history
git blame, on the lines that hold a TODO ────────────────▶ the age of each TODO
the coverage report of the project's own test run ───────▶ the lines a test reached
```

---

## Which files

It reads the files every other part of broom reads: tracked and untracked code files, with dependencies, build output, generated code and the paths `.broom.json` excludes left out. Paths on the command line narrow it.

It needs git and nothing else. No linter runs.

---

## One pass over each file

Each file is read from its syntax tree: Python's with the standard library's `tokenize` and `ast`, Swift's with its compiler and SourceKit, and the rest with ast-grep's rules, one run for many files. For each file it gives the non-blank lines, the test cases and skipped tests, the lint suppressions and the TODO comments. A marker counts only in a comment the tree isolated, so one inside a string never counts. A Rust suppression is an `allow` attribute. Without ast-grep a Go, Rust, TS/JS or CSS file is left unread, and the output says so.

Test cases and skipped tests are read in test files only, except in Rust, where tests sit beside the code. A conditional skip, such as a test that skips when a tool is missing, counts as skipped. A file under a test folder is a test file whatever its name, so a helper there counts as one, and the output says how many of them hold test cases. The cases are counted from the tree, so the number can differ from what a test runner collects.

A TODO counts when the word marks the comment: it opens the comment, or a colon or a bracket follows it. The word in a comment's prose is left out, and so is a file's name such as `TODO.md`.

A code file is paired with a test file by name, anywhere in the repo. Rust and CSS take no part in the pairing.

---

## Coverage

broom runs no tests. It looks for a coverage report at the usual places under the repo's root and reads the one written last. The form is told by how the report starts: Cobertura XML, lcov, Go's cover profile or the JSON of coverage.py.

A report names files its own way: from the folder the tests ran in, by an absolute path on another machine or by Go's import path. Each name is matched to a file of the repo by itself, then under the report's source folders, then by its longest end that is a file here. A name that matches no file is dropped.

A line counts as reached when any entry for it says so, since a report can hold one file once per test run. Go's profile counts statements per block. Test files are left out.

A report over 32 MB, or one that can't be read as any of the four forms, is named as unread. An XML report that declares entities is refused, since no coverage tool writes one.

---

## History

One `git log` over the period gives the commits per file and the pairs of files that changed in the same commit. A commit of more than 30 files is left out of the pairs, since it says nothing about which two files belong together.

---

## The age of a TODO

`git blame` runs only on the files that hold a TODO comment, on 200 such lines at most, the files with most first. When the cap is hit, the output says so. An untracked file is not blamed. Each blamed line keeps the day it was written, and the oldest are listed with it.
