# 039. A length counts code lines, not the lines of a file

Decided: 2026-11-24

---

## The problem

A length counted every line of a function, a type or a file, comments and blank lines among them. A change that added only a doc comment to a long file was blocked for growing it. broom asks for doc comments with `missing_docs`, and then counted them against the code.

The linters also disagreed. SwiftLint and clippy leave comments and blank lines out, and neither can be set otherwise. funlen and oxlint counted both, as broom set them.

---

## The choice

A length is a count of code lines. A code line holds something besides space outside a comment. A Python docstring is a comment.

broom reads the code lines of each file once, from its syntax tree. Every length is counted from that one set: a file's, a function's and a type's, whether a change grew one, and whether a changed line touches one. `broom stats` counts the same lines.

Blank lines are left out with the comments. It is the one way every language can be counted alike, since SwiftLint and clippy count no other way.

---

## Not chosen

- **Measure every line, then subtract the comment lines**: The user rejected it on 2026-11-24. Each place that counts lines needs its own subtraction, and one place missed counts comments again.
- **Each linter's own setting**: funlen took a block comment of 2 lines for 1 and has no setting for blank lines. Neither funlen nor oxlint's count says where a function ends, which the touched hint needs.
- **Comments out, blank lines in**: Swift and Rust can't be counted that way, so one bar would not hold in every language.
- **Lower limits in the same change**: The limits stay where they were. Whether they come down is the user's to decide.

---

## Consequences

Every length reads smaller than before. broom's own `lib/` holds 9,227 code lines in 13,950 lines. The limits didn't move, so the bar is looser by as much as a file holds comments and blank lines.

A finding reads `is 60 code lines long`. A length accepted before is asked once more, since its message holds the new number.

Go's function length is read by broom from the syntax tree, and funlen no longer runs. It counts from the `func` line through the closing brace, where funlen counted the body alone.

A function or a type keeps the lines it takes beside its length, since the two now differ. SwiftLint and clippy give a length and no span, so a touched Swift or Rust function is found over fewer lines than it takes.

Without ast-grep, or without SourceKit for Swift, comments can't be told from code in that language. Every line that isn't blank then counts, and a note says so.

`duplicate_lines` is no length. jscpd counts the lines of a repeated block its own way, comments among them.
