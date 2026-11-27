# 054. A test that asserts nothing is a broad test assertion

Decided: 2026-11-27

---

## The problem

A test with no assertion passes whatever the code does. [051: A test is judged by what it proves, not by how it reads](051-tests-judged-by-what-they-prove.md) named four smells that let a test lie, and this one was missing. The user agreed on 2026-11-27 to count it.

---

## The choice

It is a form of `broad_test_asserts`, an assertion that any outcome passes: no assertion is the broadest one. Its finding says "a test that asserts nothing", apart from a broad assertion, and it counts when a change adds one.

| Language | A test that asserts nothing | Level |
|---|---|---|
| TS/JS | flagged by both oxlint's `jest/expect-expect` and `vitest/expect-expect`, since Jest's rule doesn't know Vitest's `assert` | hint |
| Go | a `Test…(t *testing.T)` whose `t` the body never names: only a panic can fail it | hint |
| Python | a test function with no `assert`, no call of an `assert…`, `expect…` or `fail…` name, no `pytest.raises`, `warns` or `fail`, and no `raise` | nit |
| Rust | a `#[test]` with no `assert…!`, `panic!`, `unreachable!` or `todo!`, no `unwrap` or `expect`, no `?` and no `#[should_panic]` | nit |
| Swift | an XCTest `test…` method or a `@Test` function with no `XCTAssert…`, `XCTFail`, `XCTUnwrap`, `#expect`, `#require` or `try` | nit |

In Python and Swift a call to a function of the same file that asserts, directly or through another, counts as asserting, since a test may hand its checks to a helper beside it. In Python a function that returns a value is no test, as pytest warns of one, so a factory named `test_…` is left out. A helper of another file can't be seen, so in these three languages the finding is a guess and a nit.

---

## Not chosen

- **A smell of its own**: The bar has 27 smells, named in the README's hero and in each language's table, and this one differs from a broad assertion only in how broad.
- **A hint in every language**: A helper in another file that asserts would be taken for none, and noise teaches Claude to override broom.

---

## Consequences

The fix line of `broad_test_asserts` covers both: assert the specific outcome the test is for, the exact error, message or value.

A test skipped by a decorator with no condition is left out, since it is a skipped test already.

1 gap:

- Rust doesn't read a helper of the same file, since its rule is one ast-grep pattern, so a Rust test that asserts only through one is told as a nit.
