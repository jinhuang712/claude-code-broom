---
name: sweep
description: Format, lint and type-check the repo's uncommitted changes (or given paths) with broom, the same sweep broom runs on git commit, and report what is left. Use for /broom:sweep, or when asked to clean up, format or lint the current changes.
argument-hint: "[--check] [--staged] [paths...]"
---

Run it from the repository the user means:

```bash
broom sweep $ARGUMENTS
```

- `broom` is on the PATH while the plugin is enabled.
- With no paths it takes every file changed against HEAD plus untracked files; `--staged` takes only the index,
  and paths narrow either. `--check` reports without formatting.
- Lint findings count on changed lines only; compile and type errors count anywhere. Unlike the commit hook,
  it also shows issues accepted earlier.
- Relay the report. Fix the findings only if the user asked for fixes.
