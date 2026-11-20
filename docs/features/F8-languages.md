# F8: Languages

```
F8: Languages
├── F8.1: Go
├── F8.2: TS/JS
├── F8.3: Rust
├── F8.4: Python
├── F8.5: CSS, SCSS and Less
└── F8.6: Swift
```

broom runs each language's own tools. They come from the project's `node_modules/.bin` first, then PATH.

| | Format | Lint | Type or compile check |
|---|---|---|---|
| Go | gofmt | golangci-lint | golangci typecheck · `go vet ./...` |
| TS/JS | the project's biome, oxfmt or prettier | the project's oxlint, eslint or biome | `tsc --noEmit` |
| Rust | rustfmt | cargo clippy | clippy errors |
| Python | ruff format | ruff check | — |
| CSS · SCSS · Less | the project's biome, oxfmt or prettier | the project's stylelint, biome or ESLint | — |
| Swift | the project's swift-format or SwiftFormat | SwiftLint | `swift build --build-tests` |

broom has 27 smells, and each language measures a share of them:

| | Measures | Lacks |
|---|---|---|
| Python | 27 | — |
| TS/JS | 27 | — |
| Go | 24 | 3 that the language rules out |
| Swift | 25 | 2 that the language rules out |
| Rust | 27 | — |
| CSS · SCSS · Less | 2 | 25 |

- **Stance**: [The project's tools, not ours](../PHILOSOPHY.md#whose-rules-decide-what-is-clean)
- **What each smell is**: [F4: Smells](F4-smells.md)

---

## F8.1: Go

At commit the project's golangci formatters, gofumpt and goimports, format too.

Go has 24 of the smells. The language rules out the other 3: a nested ternary, which it has no operator for, and both cycles, which its compiler refuses.

---

## F8.2: TS/JS

Without a project linter, oxlint runs with broom's defaults, type-aware. A solution-style tsconfig is type-checked per referenced config.

---

## F8.3: Rust

A crate is checked whole, by one run of clippy that also measures the smells. A cold `cargo clippy` can time out.

Rust has all 27 of the smells: 8 sized ones, 16 that count by occurrence, the 2 cycles and dead code. It has no ternary operator, but its `if` is an expression, as Python's conditional expression is, so an `if` that gives a value and holds another in a branch is its nested ternary. The smells no linter covers are read from the syntax tree with ast-grep.

---

## F8.4: Python

Python is formatted only where ruff is configured. It has no type check in the sweep, and pyright shows Claude type errors as it edits.

---

## F8.5: CSS, SCSS and Less

Without a project linter, stylelint runs with broom's defaults, which report errors and not style. biome and ESLint with `@eslint/css` lint plain CSS only.

6 limits:

- The defaults accept Tailwind's directives and functions at v3 and v4, and CSS modules.
- They skip build output and `*.min.css`.
- Without the SCSS and Less configs installed in the project those files aren't linted, with a note.
- Sass's indented syntax and Stylus aren't covered.
- `<style>` blocks in `.vue` or `.svelte` files and CSS-in-JS aren't covered.
- In Less, each detached ruleset call such as `@r();` draws a false positive from the hex rule.

---

## F8.6: Swift

Swift has 25 of the smells. The language rules out the other 2, both cycles: a Swift file imports modules and never another file, and SwiftPM refuses modules that depend on one another. Layers inside one module can still go the wrong way, and no import says so.

SwiftLint runs with the project's `.swiftlint.yml`, else with broom's defaults. The defaults are bug-finders and not style: the rules SwiftLint files under "lint" and "performance", plus `force_cast` and `force_try`. Naming, length and layout rules are off, and CocoaPods, Carthage and `.build` code is skipped.

4 limits:

- The compile check and deprecated calls cover SwiftPM packages only, since an Xcode project needs `xcodebuild` with a scheme and minutes.
- It counts errors only, because SwiftPM prints warnings just for the files it recompiles.
- With macOS's Command Line Tools and no Xcode the check builds the sources and leaves the tests out, with a note.
- A cold `swift build` can time out.
