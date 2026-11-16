# Setup

This part finds what a repo needs and lacks, and remembers what the user answered. It exists because a hook with no tool behind it does nothing and says nothing.

---

## The scan

`broom doctor` scans for marker files such as `go.mod`, `package.json`, `Cargo.toml` and `pyproject.toml`, three levels deep and at up to 20 projects per language. It lists the tools each language needs and runs each one to prove it works. That catches a rustup proxy without its component, and macOS's `swift` shim without Xcode or the Command Line Tools.

CSS has no marker file. It goes by the `.css`, `.scss` and `.less` files git tracks at any depth, each counted with its nearest `package.json`, else the repo root. Swift goes by its files too, since an Xcode app has no `Package.swift`. One `git ls-files` lists both.

Untracked files are left out: listing them walks the working tree, about 160 ms on a 6,000-file repo against 25 ms for tracked files.

The scan flags missing configs, collapsed to one fix at the repo root since configs are found by walking up. It flags plugins whose language servers claim the same files as broom's.

---

## At session start

The SessionStart hook runs a cached doctor. The cache key includes the modification time of every PATH directory, so installing a tool invalidates it. When there are gaps it asks Claude, once per session, to offer `/broom:setup`.

---

## Answers

`broom setup --done` or `--dismiss` stores a hash of the repo's gaps, and each gap's kind in a user-wide list. A kind is the language, the role, the tool and the status, with no path. A repo is raised only when it has a gap of a kind not in that list.

`doctor --json` offers `fix_global`, the same fixes with JS tools installed globally instead of as devDependencies. `broom setup --reset` clears the list.

- [022: Setup answers are remembered by kind](decisions/022-answers-by-kind.md)

---

## Fix commands

Fixes come out as ready commands. JS/TS and CSS tools install as devDependencies with the project's package manager, with `-w` or `-W` at pnpm and yarn workspace roots. The rest go through brew, go install, rustup, uv, npm, swiftly or `xcode-select --install`.
