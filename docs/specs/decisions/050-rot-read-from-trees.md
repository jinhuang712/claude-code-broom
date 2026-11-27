# 050. More rot is counted, each from what parses it

Decided: 2026-11-27

---

## The problem

The user picked on 2026-11-27 that broom finds more kinds of rot, none of them by the clock and none by a guess. Five kinds were counted by nothing, and Go's commonest way to drop an error went unseen:

- Unsafe code, which steps outside what the compiler checks.
- Type escapes across the repo, which a change was told about but no counter kept.
- Broken links in Markdown, which go stale when a file moves.
- Lint suppressions in YAML, shell and HTML comments, which loosen a linter as a code comment does.
- The largest tracked files, such as a binary committed by mistake.
- A Go error assigned to `_`.

---

## The choice

| Rot | Where it shows | Read from |
|---|---|---|
| Unsafe code | a check-up counter and `broom stats` | ast-grep for Rust and Go, the compiler's tree for Swift |
| Type escapes | a check-up counter | the session scan's `type_escape` smells |
| Broken Markdown links | a check-up counter and `broom stats` | broom's own reader of Markdown's link syntax |
| Suppressions in YAML, shell and HTML | the suppressions counter and a self-waiver | ast-grep's comment nodes of those grammars |
| The largest tracked files | `broom stats` | the file system's sizes |
| A Go error dropped with `_` | a `swallowed_error` nit | golangci-lint's `errcheck` with `check-blank`, kept only where a `_` stands |

A Go error dropped with `_` is a nit, as Rust's `let _ =` is: `_ = conn.Close()` is often meant, and the tool can't tell which.

Markdown has no grammar in ast-grep and no parser in Python's standard library. So broom reads Markdown's link syntax itself, leaving code spans, fenced code, HTML and comments out, and uses no regular expression.

---

## Not chosen

- **Links checked over the network**: A link with a scheme is left out, since a lookup would send the repo's links out and turn on the server's answer.
- **errcheck's other checks**: A call whose error is never assigned is the project's linter's to report, and broom's lint config already does.
- **A counter for the largest files**: A big file is told once in `broom stats`, and its size changes with no rot.

---

## Consequences

Each counter is new to the record a check-up keeps, so its first number is taken silently.

The Go error dropped with `_` was taken back out in 0.30.2, the day it shipped. In a real Go repo most of what it flagged was cleanup, such as `_ = x.Close()` in a `defer`, or an encode, such as `_ = json.Marshal(v)`: the form errcheck itself asks for. That broke the rule of [042: A Go rule flags what its message says](042-go-rules-flag-their-message.md), which flags nothing the standard library writes as a matter of course. A dropped error of a call that does work waits in TODO.

3 gaps:

- A Markdown link inside an indented code block is read as a link.
- A link into a git submodule counts as broken.
- Rust's `unsafe trait` and `unsafe extern` blocks are not counted.
