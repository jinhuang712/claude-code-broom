# Changelog

## 0.5.0

- CSS and SCSS are linted: with the project's stylelint, biome or ESLint with `@eslint/css` (the last two plain
  CSS only), else with stylelint and broom's defaults. The defaults report errors, not style:
  stylelint-config-recommended's rules for CSS, `stylelint-config-recommended-scss` for SCSS, both accepting
  Tailwind (v3 and v4) and CSS modules. Without that SCSS config in the project, SCSS is skipped with a note.
- A language server for `.css` and `.scss` (vscode-css-language-server), set up to accept Tailwind's at-rules and
  `composes`.
- `format_scope=function` widens CSS to the innermost rule around each changed line.
- `broom doctor` finds CSS and SCSS at any depth and reports their linter, formatter and language server;
  `broom init` turns on oxfmt for CSS outside JS projects. Formatting itself is unchanged: CSS and SCSS were
  already formatted by the project's biome, oxfmt or prettier.

## 0.4.0

- `format_scope=function`: widens the changed lines to the functions around them, asking the language servers in
  broom's `.lsp.json` (`documentSymbol`). Falls back to changed lines, with a note, when no server answers.
- Per-repo `.broom.json`: `format_on`, `check_on` and `format_scope` override the user settings in that repo;
  `exclude` globs keep generated or vendored paths out of everything. `broom doctor` validates the file.
- Runs on Python 3.9+ (tested on macOS's system Python). MIT `LICENSE`.

## 0.3.0

- `broom doctor`: languages, missing or broken tools (a rustup proxy without its component, TypeScript older than
  7 for the language server), missing configs, dependencies not installed, and plugins whose language servers
  compete with broom's, with the commands that fix each. One root config covers a monorepo.
- A SessionStart hook runs the doctor (cached, ~0.1 s) and, when the repo has gaps, asks Claude to offer
  `/broom:setup`. Once per session; not again after `broom setup --done` / `--dismiss` until the gaps change.
- `/broom:setup` replaces `/broom:init`: it asks what to install (JS/TS tools as devDependencies, with `-w`/`-W`
  at pnpm/yarn workspace roots), whether to turn formatting on, when broom runs, and the format scope.
- `format_scope` option: `changed` (default) keeps only the formatter's edits on changed lines, for every
  formatter; `file` formats whole files.
- `/broom:sweep` takes plain language; `broom sweep` gained `--staged`, `--base REV`, `--all` (report only unless
  `--fix`), `--scope` and `--include-known`, and summarizes big results.
- `broom known` lists and clears accepted issues; sweeps say how many are hidden.
- Missing tools never block a commit; the report suggests `/broom:setup`.
- Solution-style tsconfigs (`"files": []` plus references) are type-checked per referenced config.
- Bash-run `broom` reads the plugin options from the settings file, since only hooks get them as variables.

## 0.2.0

- Renamed from `lint@claude-code-lint` to `broom@claude-code-broom`.
- Runs on `git commit` by default: formats the files the commit takes, re-stages them, lints and type-checks,
  and denies the commit while issues remain. Partially staged files are left unformatted; `--no-verify` skips.
- `userConfig` options `format_on` (commit / edit / off) and `check_on` (commit / stop / off), shown in `/config`.
  The per-edit and end-of-turn hooks now exit in ~15 ms unless enabled.
- `bin/broom` on the Bash PATH (`sweep`, `fmt`, `init`); skills call it instead of script paths.
- Hooks use exec form; no more "re-read the file" message after formatting.
- End-to-end test suite in `tests/`.

## 0.1.0

- Format on every edit, lint gate at every stop, language servers for Go, TS/JS, Rust and Python.
