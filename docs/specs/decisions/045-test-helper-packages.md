# 045. A Go test-helper package is test code

Decided: 2026-11-27

---

## The problem

Go keeps test helpers in packages of their own, next to what they test: `net/http/httptest`, `testing/iotest`, `testing/fstest` and `log/slog/slogtest`. Their files don't end in `_test.go`, so broom measured them as library code. The same lines in a `_test.go` file are measured as tests.

In one repo a contract suite that its adapters run lived in such a package. Its fixtures name log positions, and `broom smells` listed each as a magic number. A worker named every position to reach zero smells, and the suite got harder to read: its failure texts still say the numbers.

---

## The choice

A test file is told by its path, and 2 helpers join the names test runners collect:

| Path | Example | Why it is test code |
|---|---|---|
| a Go file directly in a folder whose name ends in `test` | `cache/cachetest/fixtures.go` | Go names a package after its folder, and the name says the package serves tests |
| `conftest.py` anywhere | `pkg/conftest.py` | pytest loads it only for tests |

Such a file gets what a test file gets:

| Rule | Code | Test code |
|---|---|---|
| `file_lines` | 400 and 1000 | 800 and 2000, and `test_limits` |
| `complexity` · `magic_numbers` · `missing_docs` | count | don't count |
| a repeated block with another test file | a smell | a duplicate test |
| `untested_file` | asked for | never |
| `broom stats` | code lines | test lines |
| Go's `broad_test_asserts` | doesn't count | counts |

A test function is still held to the code's length.

---

## Not chosen

- **The import path**: Its last part is the folder's name, so it says nothing more.
- **A package only tests import**: It needs the module's whole import graph at every check. `httptest` has importers outside tests and is still test code.
- **The package clause**: A path is all most callers of the rule have, and Go names the package after its folder.
- **The same in every language**: Only Go and pytest fix the name. TS/JS's `test-utils`, Swift's `TestSupport` targets and Rust's helper crates follow habits, not a rule, so they wait in TODO.

---

## Consequences

Go's `broad_test_asserts` now counts in every test file, a file under `tests/` and a helper package among them, where it counted in `_test.go` files alone.

2 gaps:

- A Go folder named `latest`, `attest` or `contest` reads as test code.
- A package of fakes that only tests import, such as `fakeclock`, is still code.

Since 2026-11-27 Jest's and Vitest's helpers are test code too: a file under `__mocks__/`, and the setup files `setupTests.*`, `jest.setup.*` and `vitest.setup.*`, which the runners name.
