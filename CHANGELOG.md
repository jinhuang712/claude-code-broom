# Changelog

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
