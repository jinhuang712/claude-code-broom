# 038. Smells are read from a syntax tree: the language's own parser, else ast-grep

Decided: 2026-11-20

---

## The problem

Where a linter has no rule for a smell, broom read the smell from the text itself: braces counted, keywords matched and regular expressions in SwiftLint custom rules. A text pattern holds only for the code its author thought of. A raw string, a new attribute or a call split over two lines breaks it without a word. The user asked that day for checks that rest on a mechanism and hold up as code varies.

---

## The choice

A smell no linter covers is read from a syntax tree, in this order:

1. The language's own parser, where it runs with no build: Python's `ast` in broom's own process, and the Swift compiler's `-dump-parse` with JSON output.
2. ast-grep for the rest: Go, Rust and TS/JS. It runs structural rules on tree-sitter grammars it bundles, and its rules live in broom's `defaults/`.

A smell that a language's parser shows as unparsable code is not guessed: the region is left out with a note.

---

## Not chosen

- **ast-grep for Swift too**: Its Swift grammar failed on 182 of 14,517 Swift files of open-source projects on 2026-11-20, mostly on attributes such as `@concurrent` and `@Sendable`. The compiler's own parser read the same code in about 60 ms a file.
- **A helper built on each language's parser library**: go/ast, syn and swift-syntax need a program compiled and kept for each, and swift-syntax a build of minutes.
- **Language servers**: They give symbols and not a full tree, and they start too slowly for a hook.
- **tree-sitter's Python bindings**: They are a package, and broom runs on the standard library alone.
- **The text patterns, with more tests**: A test proves the cases its author thought of, which is the problem.

---

## Consequences

ast-grep is one more tool to install, which the doctor offers like jscpd. Without it the smells it reads go unmeasured, with a note, and nothing blocks. Its grammars lag their languages: on the same day 31 of 5,000 Rust files and 20 of 3,000 TS files held a region it couldn't parse, and 0 of 651 Go files. A rule is data and not code, so a smell's rule can change without touching broom's Python.
