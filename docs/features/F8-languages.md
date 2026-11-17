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

- **Stance**: [The project's tools, not ours](../PHILOSOPHY.md#whose-rules-decide-what-is-clean)

---

## F8.1: Go

At commit the project's golangci formatters, gofumpt and goimports, format too.

---

## F8.2: TS/JS

Without a project linter, oxlint runs with broom's defaults, type-aware. A solution-style tsconfig is type-checked per referenced config.

---

## F8.3: Rust

A crate is checked whole, by one run of clippy that also measures the smells. A cold `cargo clippy` can time out.

Rust has 16 of the smells: 6 sized ones and 9 that count by occurrence, plus dead code. It lacks magic numbers, commented-out code, globals, long types, nested ternaries and broad test assertions, which clippy has no lint for.

---

## F8.4: Python

Python is formatted only where ruff is configured. It has no type check in the sweep, and pyright shows Claude type errors as it edits.

---

## F8.5: CSS, SCSS and Less

Without a project linter, stylelint runs with broom's defaults, which report errors and not style. biome and ESLint with `@eslint/css` lint plain CSS only.

6 limits:

- The defaults accept Tailwind's directives and functions at v3 and v4, and CSS modules.
- They skip build output and `*.min.css`.
- The SCSS and Less configs must be installed in the project, or those files aren't linted, with a note.
- Sass's indented syntax and Stylus aren't covered.
- `<style>` blocks in `.vue` or `.svelte` files and CSS-in-JS aren't covered.
- In Less, each detached ruleset call such as `@r();` draws a false positive from the hex rule.

---

## F8.6: Swift

SwiftLint runs with the project's `.swiftlint.yml`, else with broom's defaults. The defaults are bug-finders and not style: the rules SwiftLint files under "lint" and "performance", plus `force_cast` and `force_try`. Naming, length and layout rules are off, and CocoaPods, Carthage and `.build` code is skipped.

4 limits:

- The compile check covers SwiftPM packages only, since an Xcode project needs `xcodebuild`, a scheme and minutes.
- It counts errors only, because SwiftPM prints warnings just for the files it recompiles.
- With macOS's Command Line Tools and no Xcode, the check builds the sources and leaves the tests out, with a note.
- A cold `swift build` can time out.
