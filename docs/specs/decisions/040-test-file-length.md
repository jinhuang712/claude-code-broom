# 040. A test file may be twice as long as a code file

Decided: 2026-11-24

---

## The problem

A test file took the length limits of a code file. `test_limits` could move them, and a repo learned that only by being stopped.

A test file is long by the cases it lists. In one repo most of the long test files were lists of short cases, and none of the code files they test was past its own limit. So a code file within its limit was tested by a file past it. Such a file can only be split by number, which [012: Tests take smell limits of their own](012-test-limits.md) found to help no reader.

A few of the long test files were long by helper code: fixtures and rigs with no test in them. Helper code is code. One such file was shortened well by moving its rig to a file of its own.

---

## The choice

A test file's `file_lines` limits start at twice the code's: 800 and 2000 where the code's are 400 and 1000. They follow the repo's `limits`, and `test_limits` still sets them outright.

Only a file's length is doubled. A test function is held to the code's length, as before.

The limits card names a limit that differs for test files beside the code's.

---

## Not chosen

- **The code's limits for a test file**: It stops a change that adds a case to the tests of a code file within its limit.
- **No length limit for a test file**: A file of helper code would grow without end.
- **Count only what lies outside the test functions**: It would free the cases and hold helper code to the code's limit. A length would then need every language's test forms, so it waits for a need.
- **A factor measured in each repo**: One bar holds in every repo.

---

## Consequences

A test file between the code's limit and twice it is no smell any more, in every repo.

A file of helper code among the tests gets the doubled limits too, since a test file is told by its path.

A repo that set `file_lines` in `test_limits` keeps what it set. `"test_limits": {"file_lines": [400, 1000]}` brings the old bar back.

A `test_limits` entry is a self-waiver when it lifts a test file past twice the code's limits, and none at or below them.

The factor rests on one repo's test files. broom's own test files all stay within the code's limit.

Since [051: A test is judged by what it proves, not by how it reads](051-tests-judged-by-what-they-prove.md) a test file past these limits is a nit and stops nothing, so the factor decides only when its length is told.
