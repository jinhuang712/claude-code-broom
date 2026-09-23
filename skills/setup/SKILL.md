---
name: setup
description: Set up broom for this repo. Finds missing formatters, linters, type checkers and language servers, asks the user, installs what they agree to, adds default configs and picks when broom runs. Use for /broom:setup, when broom's session note says the repo has gaps, or when the user asks to set up linting, formatting or language servers.
---

## 1. Diagnose

```bash
broom doctor --json
```

`items` lists every tool and config with a status: `ok`, `missing`, `broken` (on PATH but doesn't run),
`off` (no config, so broom leaves formatting alone) or `conflict` (another plugin starts a language server for
the same files). `fix` and `configure` hold the exact commands, in order. If `healthy` is true, tell the user
everything is in place, run `broom setup --done`, and stop.

## 2. Ask

Summarize the gaps in plain words, then ask with AskUserQuestion, in one call, only the questions that apply:

1. **Install the missing tools?** Show the `fix` commands. JS/TS and CSS tools go in as devDependencies of the
   project (that's what `fix` already does); mention a global install as the alternative, except for
   `stylelint-config-recommended-scss` and `-less`, which stylelint only finds in the project. Options: install
   all (recommended), let me pick, skip.
2. **Turn on formatting where it's off?** Show the `configure` commands: `broom init <dir>` adds default configs
   and never overwrites. Options: yes (recommended); yes, and reformat the whole repo now (a large diff); no.
3. **When should broom run?** Ask how they work:
   - Claude commits for me → on commit (recommended): `format_on=commit check_on=commit`
   - I commit myself → end of each turn: `format_on=commit check_on=stop`
   - Strictest → every edit and each turn: `format_on=edit check_on=stop`
4. **How much of a file should broom reformat?**
   - Only the changed lines (recommended), like an IDE's "only VCS changed text": `format_scope=changed`
   - The functions holding the changed lines (in CSS, the rules), found by the language server:
     `format_scope=function`
   - The whole file, best once the repo is fully formatted: `format_scope=file`

Ask only what applies. Never install or change anything the user didn't pick.

## 3. Act

- Run the picked `fix` and `configure` commands from the repo root, one at a time, and stop on a failure.
- Apply the trigger and scope choices for all repos:

  ```bash
  claude plugin install broom@claude-code-broom --config format_on=<value> --config check_on=<value> \
    --config format_scope=<value>
  ```

  If the user wants them for this repo only, write them to `.broom.json` at the repo root instead, for example
  `{"format_on": "commit", "check_on": "stop", "format_scope": "function"}`. It overrides the user settings in
  this repo. Paths broom should never touch (generated code, vendored code) go in `"exclude"` as globs relative
  to the repo root, for example `["vendor/**", "**/*.pb.go"]`.

- Whole-repo reformat, if picked: `broom sweep --all --fix`.
- A `conflict` means another plugin serves the same files. Offer its `claude plugin disable …` command; the
  change applies after `/reload-plugins`.

## 4. Verify and record

Run `broom doctor` again and show the result. Then:

- run `broom setup --done` when the user went through with setup, even if they left some gaps on purpose
- run `broom setup --dismiss` when they declined

Either way broom won't raise setup again for this repo until the gaps change.
