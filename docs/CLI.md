# CLI

`broom` is called by a person in a shell, by Claude through the skills, and by Claude Code and git as a hook. It is on the Bash tool's PATH while the plugin is enabled.

Status: ✅ built · ⬜ planned

---

## Commands

---

### broom sweep

**Status**: ✅

`broom sweep [--staged | --base REV | --all] [--check | --fix] [--include-known] [--scope SCOPE] [paths...]` formats, lints and type-checks a set of files.

| Flag | Means | Default |
|---|---|---|
| none | the uncommitted changes | — |
| `--staged` | only the staged files | off |
| `--base REV` | the files changed since REV | off |
| `--all` | the whole repo with every line counted | off |
| `--check` | report only | off |
| `--fix` | with `--all`, also format every file | off |
| `--include-known` | show known issues and let them count | off |
| `--scope` | `changed` · `function` · `file` | the `format_scope` setting |
| `paths` | narrow the scope to these | the repo |

**Called by**: a person and the `/broom:sweep` skill.

**Prints**: stdout gets `formatted <file> (<tool>)` lines, `note:` lines, the report or `broom: clean (N file(s))`, the count of known issues hidden and the smell report. stderr gets only `broom: unknown revision '<REV>'`.

**Fails**: exit 1 when a finding counts or a smell is found, hints included. Exit 1 for an unknown `--base`.

**Example**: `broom sweep --staged` prints `broom: clean (3 file(s))`.

---

### broom fmt

**Status**: ✅

`broom fmt [--scope SCOPE] [paths...]` formats only.

| Flag | Means | Default |
|---|---|---|
| `--scope` | `changed` · `function` · `file` | the `format_scope` setting |
| `paths` | also format these files | the changed files |

**Called by**: a person.

**Prints**: stdout gets `formatted <file> (<tool>)` lines, `note:` lines or `broom: nothing to format`. stderr gets nothing.

**Fails**: it always exits 0.

**Example**: `broom fmt src/app.ts` prints `formatted app.ts (oxfmt)`.

---

### broom doctor

**Status**: ✅

`broom doctor [--json]` lists a repo's languages, tools, configs and conflicts with the commands that fix them.

| Flag | Means | Default |
|---|---|---|
| `--json` | print one JSON object | off |

**Called by**: a person and the `/broom:setup` skill.

**Prints**: stdout gets one line per item with its status, git's pre-commit hook among them, a `To fix:` list, a `To turn formatting on:` list, and `All set.` when healthy. stderr gets `broom: not inside a git repository`.

**Fails**: exit 1 when an item is not ok, and outside a repo.

**Example**: `broom doctor` in a healthy repo ends with `All set.`.

---

### broom init

**Status**: ✅

`broom init [dir] [--dry-run]` adds default configs where a project has none. It never overwrites.

| Flag | Means | Default |
|---|---|---|
| `dir` | the project directory | the git root |
| `--dry-run` | say what would be added and write nothing | off |

**Called by**: a person and the `/broom:setup` skill.

**Prints**: stdout gets `added <file>` or `would add <file>` per config, a suggested ruff block for a `pyproject.toml` without ruff settings, or `broom: <dir> already has its configs`. stderr gets nothing.

**Fails**: it always exits 0.

**Example**: `broom init --dry-run` prints `would add .oxlintrc.json`.

---

### broom smells

**Status**: ✅

`broom smells [paths...] [--base REV] [--top N] [--json] [--dismiss]` ranks the code smells of the repo or some paths.

| Flag | Means | Default |
|---|---|---|
| `paths` | limit to these | the repo |
| `--base REV` | only what the changes since REV made worse | off |
| `--top N` | how many hotspot files and smells to list | 10 |
| `--json` | print JSON | off |
| `--dismiss` | quiet the session note until the severe count grows | off |

**Called by**: a person and the `/broom:clean` skill. Claude runs `--dismiss` when the user says not now.

**Prints**: stdout gets a first line with the counts, then `Hotspots:` and `Worst smells:` blocks and `note:` lines. stderr gets `broom: not inside a git repository` or `broom: unknown revision '<REV>'`.

**Fails**: exit 1 outside a repo and for an unknown REV. It exits 0 whether or not smells are found.

**Example**: `broom smells src --top 3` prints `[broom] 12 code smell(s) in ~/code/app` and three files.

---

### broom known

**Status**: ✅

`broom known [paths...] [--accept WHY] [--clear]` lists, accepts or clears known issues.

| Flag | Means | Default |
|---|---|---|
| none | list the known issues under `paths` | the repo |
| `--accept WHY` | accept what the last blocked commit or turn end showed, with the reason | off |
| `--clear` | remove the known issues under `paths` | off |

**Called by**: a person, and Claude when a block message offers `--accept`.

**Prints**: stdout gets one line per known issue with its location, tool, rule, message, date and reason. Accept prints `broom: accepted N issue(s) as known (WHY); commit again`, or `stop again` after a turn-end block. stderr gets the refusals.

**Fails**: exit 1 when there is no blocked commit or turn end to accept, when WHY is empty, when `BROOM_NO_ACCEPT` is set and outside a repo.

**Example**: `broom known --accept "predates this change"` prints `broom: accepted 2 issue(s) as known (predates this change); commit again`.

---

### broom report

**Status**: ✅

`broom report [paths...] [--days N] [--all] [--json]` prints what broom stopped, what was fixed and what went through.

| Flag | Means | Default |
|---|---|---|
| `paths` | limit to these files or directories | the repo |
| `--days N` | how far back to look | 30 |
| `--all` | every repo in the ledger | off |
| `--json` | print JSON | off |

**Called by**: a person and Claude.

**Prints**: stdout gets a line of totals with the fix rate, then a table per rule, the self-waivers by kind, the skips by tool and the median and longest seconds per check. With nothing recorded it prints `broom: nothing recorded for <repo> in the last N days`. stderr gets `broom: not inside a git repository`.

**Fails**: exit 1 outside a repo without `--all`.

**Example**: `broom report --days 7` prints `blocked 41, fixed 33, let through 8, still open 0` with the fix rate, then the rules behind it.

---

### broom install-hook

**Status**: ✅

`broom install-hook` adds git's pre-commit hook to the repo.

**Called by**: a person.

**Prints**: stdout gets `broom: added <path>`, or the line to add when another tool's hook is there. stderr gets `broom: not inside a git repository`.

**Fails**: exit 1 when another tool's hook is present, and outside a repo.

**Example**: `broom install-hook` prints `broom: added .git/hooks/pre-commit`.

---

### broom setup

**Status**: ✅

`broom setup (--done | --dismiss | --reset)` records the setup decision.

| Flag | Means | Default |
|---|---|---|
| `--done` | setup is done for this repo | — |
| `--dismiss` | setup was declined for this repo | — |
| `--reset` | forget every answer in every repo | — |

**Called by**: a person and the `/broom:setup` skill.

**Prints**: stdout gets `broom: setup done` or `broom: setup dismissed`, plus how many gaps were left. stderr gets `broom: not inside a git repository`.

**Fails**: exit 1 for `--done` or `--dismiss` outside a repo.

**Example**: `broom setup --reset` prints `broom: forgot 3 setup answer(s)`.

---

### broom hook

**Status**: ✅

`broom hook <event>` handles one hook event. It is left out of `--help`.

The 8 events: `commit` · `edit` · `prompt` · `stop` · `subagent-stop` · `session` · `session-scan` · `pre-commit`.

**Called by**: Claude Code through `hooks/hooks.json`, and git through the pre-commit script.

**Prints**: stdout gets one JSON object when there is something to say. `commit` denies with a reason or adds context. `stop` and `subagent-stop` block with a reason or give a system message. `session` and `session-scan` add context. stderr gets the denial text for `pre-commit`.

**Fails**: `pre-commit` exits 1 on a denial. Every other event exits 0, also when a handler raises and when the hook gives up.

**Example**: `broom hook stop` with a clean turn prints nothing.

---

### broom lsp

**Status**: ✅

`broom lsp typescript` picks the TypeScript language server and replaces itself with it. It is left out of `--help`.

**Called by**: Claude Code through `.lsp.json`.

**Prints**: stdout belongs to the server. stderr gets `broom: TypeScript language server: <why>`.

**Fails**: exit 1 when no server is found.

**Example**: `broom lsp typescript` starts typescript-language-server.

---

## Global flags

| Flag | Means | Default |
|---|---|---|
| `--version` | print `broom <version>` | — |
| `-h` | print help | — |

---

## Exit codes

| Code | Means |
|---|---|
| 0 | done, with nothing that counts |
| 1 | a finding counts · a repo is not healthy · a refusal · not inside a git repository |
| 2 | a wrong flag or a missing command |

An uncaught error exits 1 with a traceback.

---

## Output formats

3 commands print JSON a script relies on:

- **`broom doctor --json`**: `version` · `repo` · `languages` · `items` · `fix` · `configure` · `fix_global` · `configure_global` · `healthy` · `settings`.
- **`broom smells --json`**: `repo` · `base` · `total` · `severe` · `hints` · `hotspots` · `smells` · `notes`.
- **`broom report --json`**: `days` · `repos` · `blocked` · `fixed` · `let_through` · `open` · `how` · `fix_rate` · `rules` · `waivers` · `skips` · `seconds` · `errors`.

Each item of `smells` holds `file` · `line` · `smell` · `level` · `text` · `was`. `was` is null for a new smell.

---

## Environment

| Variable | Means | Default |
|---|---|---|
| `CLAUDE_PLUGIN_OPTION_<NAME>` | a user setting, read after the repo's `.broom.json` | the setting's default |
| `CLAUDE_CONFIG_DIR` | where Claude Code's settings file is read | `~/.claude` |
| `CLAUDE_PLUGIN_DATA` | the data directory | `~/.claude/plugins/data/broom-claude-code-broom` |
| `CLAUDE_PROJECT_DIR` | the base for relative paths from Serena's edit tools | unset |
| `BROOM_HOOK_SECONDS` | the time the commands of one hook run share | 25 |
| `BROOM_NO_ACCEPT` | any value but `0` turns `known --accept` off | unset |
| `GIT_DIR` · `GIT_WORK_TREE` | ask git for the repo root instead of walking up | unset |
| `GIT_CONFIG_COUNT` | when set, broom adds no git config of its own | unset |
| `GOMAXPROCS` · `RAYON_NUM_THREADS` · `CARGO_BUILD_JOBS` | when set, broom leaves a tool's thread count alone | a quarter of the cores in a hook |
