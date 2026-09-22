---
name: init
description: Add broom's default lint and format configs to the current project, so broom formats and lints it by the project's own rules
disable-model-invocation: true
---

1. Preview, then apply:

   ```bash
   broom init --dry-run
   broom init
   ```

   It never overwrites. It adds `.golangci.yml` (with gofumpt and goimports) for Go, `.oxlintrc.json` and
   `.oxfmtrc.json` for JS/TS when the project has no linter or formatter config, and `ruff.toml` for Python.
   Formatting JS/TS and Python only happens in projects that configure a formatter, so this is what turns it on.
2. If it reports that `pyproject.toml` has no ruff settings, add the printed `[tool.ruff.lint]` table to it.
3. Tell the user what was added. Reformatting the files already in the repo (`oxfmt .`, `golangci-lint fmt`,
   `ruff format .`) makes a large diff: offer it, don't run it.
