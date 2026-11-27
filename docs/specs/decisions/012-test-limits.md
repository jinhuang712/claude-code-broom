# 012. Tests take smell limits of their own

Decided: 2026-11-15

---

## The problem

Tests grow long by listing cases, not by doing more. One repo with file limits of 150 and 200 lines for its source split a test file into four numbered parts to fit, which helped no reader.

---

## The choice

`.broom.json` `test_limits` moves the limits for test files on top of `limits`. In tests, complexity and magic numbers don't count, and neither do the length or complexity of `describe`, `it` and `test` callbacks.

---

## Not chosen

- **One set of limits for all files**: It pushed a repo to split a test file by number.

---

## Consequences

Long test functions still count.

Since [040: A test file may be twice as long as a code file](040-test-file-length.md) a test file's length starts at twice the code's, and `test_limits` moves it from there.

Since [051: A test is judged by what it proves, not by how it reads](051-tests-judged-by-what-they-prove.md) a long test function is a nit, and these limits decide only when a test's shape is told.
