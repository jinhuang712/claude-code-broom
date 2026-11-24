# F7: Settings

```
F7: Settings
├── F7.1: User settings — four choices in /config
└── F7.2: Per-repo file — .broom.json
    ├── F7.2.1: exclude
    ├── F7.2.2: legacy
    ├── F7.2.3: limits and test_limits
    ├── F7.2.4: smells_off
    └── F7.2.5: test_commands
```

Settings start at defaults that suit most people and are never asked. The user changes one when they disagree.

---

## F7.1: User settings

Four settings sit in `/config`, each with a default.

| Setting | Default | Other values | Why it exists |
|---|---|---|---|
| `format_on` | `edit` | `commit` · `off` | some want a file left as written until a commit |
| `check_on` | `stop` | `commit` · `off` | a user who commits by hand gets no commit check |
| `format_scope` | `changed` | `function` · `file` | a one-line fix shouldn't reformat a file |
| `smells` | `on` | `off` | smells are broom's bar and not the project's |

- **Stance**: [Ask, don't assume](../PHILOSOPHY.md#who-decides-what-is-installed-or-changed)
- **How it works**: [Settings](../specs/settings.md)

---

## F7.2: Per-repo file

A `.broom.json` at the git root overrides the user settings for one repo. A linked worktree without one reads the main worktree's. `broom doctor` flags unknown keys and values.

```json
{ "format_scope": "function", "exclude": ["vendor/**"], "limits": { "function_lines": [60, 120] } }
```

- **Design**: [8. A repo's config holds choices, never commands](../DESIGNS.md#8-a-repos-config-holds-choices-never-commands)
- **Commands**: [broom doctor](../CLI.md#broom-doctor)
- **How it works**: [Settings](../specs/settings.md)

---

### F7.2.1: exclude

Globs relative to the root keep paths out of formatting, checks and smells entirely, such as `vendor/**` and `**/*.pb.go`.

---

### F7.2.2: legacy

Globs mark code on its way out. New code that repeats it isn't a duplicate, as during a migration.

---

### F7.2.3: limits and test_limits

`limits` moves a smell's soft and hard limit, such as `{"file_lines": [300, 500]}`. `test_limits` moves them again for test files. A test file's `file_lines` starts at twice the code's, so with those limits it is 600 and 1000 until `test_limits` sets it.

---

### F7.2.4: smells_off

A list turns single smells off, such as `["magic_numbers", "debug_output"]`. The name `checkup` in it turns the check-up off.

---

### F7.2.5: test_commands

A list names the commands that run the project's tests when broom's own list of runners doesn't know them, such as `["just check", "bazel test"]`. broom only recognizes them and never runs one. A command added to the list is shown as a self-waiver, since whatever it names counts as a test run.
