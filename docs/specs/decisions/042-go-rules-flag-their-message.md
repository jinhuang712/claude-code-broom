# 042. A Go rule flags what its message says

Decided: 2026-11-26

---

## The problem

broom measured a real Go repository, and most of the hints of four kinds were ordinary Go. Rewriting that code to please a rule would make it worse.

4 rules flagged more than their messages say:

- **`globals`**: gochecknoglobals flags every package variable, a lookup table or a table of test cases among them. The message says a variable that a function assigns.
- **`type_escape`**: revive's `unchecked-type-assertion` flags `v, _ := x.(T)` by default. That form checks the type and can't panic, and it is how Go reads decoded JSON.
- **`debug_output`**: forbidigo flags every `fmt.Println`, and in a `package main` program a print is the program's output.
- **`bool_params`**: a setter such as `SetEnabled(id string, enabled bool)` was flagged, though its name says what the boolean sets. The standard library has the same shape in `(*http.Server).SetKeepAlivesEnabled(v bool)`.

---

## The choice

A Go rule flags what its message says, and nothing the Go standard library writes as a matter of course.

| Smell | Counts | Stays quiet |
|---|---|---|
| `globals` | a package variable that a function assigns: `x = …`, `x += …`, `x++` | a variable no function assigns · what `init` assigns · a write to a field or an element · a method call |
| `debug_output` | `print` and `println` anywhere · `fmt.Print`, `Printf` and `Println` in a library or a test file | `fmt.Print*` in a `package main` file that is no test · a print in an `Example…` function |
| `type_escape` | a type assertion with one result, `x.(T)` | the comma-ok form, `_` in place of `ok` among them · `any` |
| `bool_params` | a boolean that steers the function | a boolean of a function named `Set` or `set`, alone or before a capital |
| `broad_catch` | a `recover()` whose value is dropped | unchanged |

`globals` and `debug_output` are read from the syntax tree with ast-grep. A package's variables are those its files in one folder declare under one package name, so the variables come from every such file and the assignments from the changed ones. That needs the project's own checkout, where the other files are. The finding marks a function's first assignment of each variable, as Python's marks its `global` statement. A name a function declares itself hides the package's variable of that name in the whole function.

---

## The edge cases

4 cases, each settled by the rule's message and by the standard library:

- **An atomic counter**: `var lastID atomic.Uint32`, whose functions call `lastID.Add(1)`, stays quiet. A method call assigns nothing, as TS/JS's `module-state` counts no method call either. `go/types` and `context` hold such counters.
- **An exported default**: `var DefaultClient = &Client{}` stays quiet while no function of its package assigns it, though a caller could. `net/http` declares `DefaultClient` and `DefaultTransport` so.
- **The single-value assertion**: `x.(T)` stays a hint. It panics on the wrong type, as Swift's `as!` and Rust's `unwrap()` panic on the wrong value, and broom counts both. The standard library writes it 3,070 times outside its tests, against 2,448 comma-ok forms, so by the standard library alone it would go. One bar across languages keeps it.
- **A deliberate `recover()`**: `defer func() { _ = recover() }()` under a comment that says why is the same tree as a careless one. Only the comment differs, and broom judges no prose. It passes accepted with a reason, which is what an accept is for. The standard library drops a recovered value in 5 places outside `cmd`, in both forms.

---

## Not chosen

- **gochecknoglobals with exceptions**: It can't tell a variable a function assigns from a table.
- **No hint for the single-value assertion**: Go would then hold a looser bar than Swift and Rust for the same panic.
- **A test may force-cast, as a Rust test may unwrap**: Rust's tests are let off because clippy doesn't build them. In the other languages a test's force cast counts.
- **The setter rule in every language**: It was asked for Go. The other languages wait in TODO.
- **A recover told apart by its comment**: That reads prose, which broom leaves to Claude.

---

## Consequences

golangci-lint's typed run lost forbidigo and gochecknoglobals. Without ast-grep, Go's `globals` and `debug_output` go unmeasured, with a note.

A print is counted in the copy of the changed files now, as the other occurrence smells are. An edited line that keeps its print adds nothing, where before it counted as added.

Since 2026-11-27 a setter's boolean is left out in every language, and a variable another package assigns, as in `pkg.Default = v`, counts in the file that assigns it.

2 gaps:

- A name a function declares in one block hides the package's variable in its other blocks too, so an assignment before the declaration is missed.
- A `print` function of a package's own and an `fmt` imported under another name are read as Go's.
