# Format scopes

This part decides how much of a file a formatter may change. It exists so that a one-line fix never turns into a reformatted file.

3 scopes:

- **`file`**: The formatter's output is kept as is.
- **`changed`**: The whole file is formatted and compared with the original, and every hunk that doesn't touch a changed line is undone.
- **`function`**: The changed lines are first widened to the outermost function or method around them.

---

## Changed

Line-for-line hunks are decided per line. Re-wrapped hunks go in or out whole. This works with every formatter, including those with no range support.

---

## Function

The ranges come from the language server's `documentSymbol`. No answer means `changed`, with a note. It costs a language server start per language, about 0.05 to 1 second.

3 languages differ:

- **CSS**: It has no functions, so the range is the innermost rule around each line. A Sass or Less mixin and a Sass `@function` count as rules.
- **Swift**: A computed property counts as a function, SwiftUI's `body` above all. sourcekit-lsp's range for a stored property covers its initializer.
- **Swift subscripts**: sourcekit-lsp doesn't report them, so there the range is the changed lines.

---

## After a formatter rewrites a file

Claude Code shows Claude the diff of any file it had read. The Edit tool accepts a changed file as long as `old_string` still matches. Serena re-reads a file whose modification time changed.

Claude Code's language servers only hear about edits made through Edit and Write. A file a formatter rewrote can show stale diagnostics until Claude edits it again.
