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
the same files). `fix` and `configure` hold the exact commands, in order; `fix_global` and `configure_global` are
the same with JS/TS tools installed machine-wide. If `healthy` is true, tell the user everything is in place, run
`broom setup --done`, and stop.

Setup answers hold in every repo. An item with `answered: true` is a kind of gap the user already left alone
somewhere; don't raise it again unless the user asks for everything. `settings` shows each setting's `value` and
its `source`: `user` or `repo` means the user already chose it.

## 2. Ask

Summarize the gaps in plain words, then ask with AskUserQuestion, in one call, only the questions that apply:

1. **Install the missing tools?** Show the commands. Options: install all, once for every repo (recommended):
   `fix_global`, a project's own `node_modules` still wins where it has one; install JS/TS and CSS tools into this
   project as devDependencies instead: `fix` (changes `package.json`, best when the team shares the setup); let
   me pick; skip. Offer the devDependency option only when `fix` and `fix_global` differ.
   `stylelint-config-recommended-scss` and `-less` stay devDependencies either way: stylelint only finds them in
   the project.
2. **Turn on formatting where it's off?** Show the `configure` commands (`configure_global` if they picked the
   once-for-every-repo install): `broom init <dir>` adds default configs and never overwrites. Options: yes
   (recommended); yes, and reformat the whole repo now (a large diff); no. Configs live in the repo, so this is
   the one question a new repo can raise again, and only if the user said yes before.
3. **When should broom run?** Skip when `settings` shows `check_on` and `format_on` with source `user` or
   `repo`. Ask how they work:
   - Claude commits for me → on commit (recommended): `format_on=commit check_on=commit`
   - I commit myself → end of each turn: `format_on=commit check_on=stop`
   - Strictest → every edit and each turn: `format_on=edit check_on=stop`
4. **How much of a file should broom reformat?** Skip when `format_scope` has source `user` or `repo`.
   - Only the changed lines (recommended), like an IDE's "only VCS changed text": `format_scope=changed`
   - The functions holding the changed lines (in CSS, the rules), found by the language server:
     `format_scope=function`
   - The whole file, best once the repo is fully formatted: `format_scope=file`

Ask only what applies. Never install or change anything the user didn't pick. If nothing applies, say so and
go to step 4.

## 3. Act

- Run the picked commands (`fix` / `configure`, or their `_global` versions) from the repo root, one at a time,
  and stop on a failure.
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

Either way the gaps left are remembered by kind for every repo: broom raises setup again only for a kind of
gap it hasn't asked about anywhere. Tell the user this, and that `broom setup --reset` makes it ask about
everything again.
