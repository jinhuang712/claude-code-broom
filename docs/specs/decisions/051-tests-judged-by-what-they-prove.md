# 051. A test is judged by what it proves, not by how it reads

Decided: 2026-11-27

---

## The problem

A test file was held to nearly the whole bar of code: its functions' lengths, its parameters, its nesting, its type escapes, its globals, its unused parameters. [012: Tests take smell limits of their own](012-test-limits.md) and [040: A test file may be twice as long as a code file](040-test-file-length.md) loosened a few limits and kept the rest.

The ledger of the author's machine held 135 blocks in test files of real repos on 2026-11-27. 122 were about a test's shape: `type_escape` 32, `globals` 20, `unused_params` 18, `function_lines` 14, `params` 12, `bool_params` 7, `complexity` 7 and 12 of lengths and repeats. One was a skipped test. Each shape block cost Claude a round on code no user runs, and the work on broom spent days on how long a test file may be. The user set that day that how well a test is written matters little.

---

## The choice

In a test file, only what lets a test pass while the code is wrong keeps its level. Every other smell there is a nit: told, and it stops nothing.

4 smells keep their level in a test file:

| Smell | Level | How it lets a test lie |
|---|---|---|
| `skipped_test` | hint | the test never runs |
| `broad_test_asserts` | hint | any error passes it |
| `swallowed_error` | block | the failure is caught and dropped |
| `suppression` | block | a rule the project set is silenced |

What [012: Tests take smell limits of their own](012-test-limits.md) leaves out of tests stays out: complexity, magic numbers, and the length and complexity of `describe`, `it` and `test` callbacks. A nit in a test file past the hard limit is a nit too, and so is an old smell in a test the change touches.

The project's own tools judge tests as before: a type error or a lint finding in a test file blocks as it does anywhere.

---

## Not chosen

- **No smell at all in a test file but the four**: The user wanted the rest still told, so that nothing is hidden.
- **Every smell a nit in a test file, the four among them**: A skip is the shortest way to make a failing suite pass, and a nit stops nothing.
- **The bar as it was**: 122 of 135 blocks in test files were about shape.

---

## Consequences

A test file's shape never stops a commit or a turn's end. A test function of 300 lines is told once as a nit.

The limits of 012 and 040 now decide only when a test's shape is told, and `test_limits` moves that.

Telling test code from code matters more: a file taken for a test gets the light bar. A file of helper code among the tests is told by its path, as before.

A nit weighs nothing in a hotspot's score, so a test file ranks there only by the four.
