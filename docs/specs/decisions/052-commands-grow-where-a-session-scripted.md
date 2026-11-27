# 052. broom answers by commands that grow where a session had to script

Decided: 2026-11-27

---

## The problem

The user asked on 2026-11-18 for a way to ask broom anything, as Code Mode lets a model write code against an API, so that the command line needn't cover every case. Six forms were on the table: more flags · a full export for a script outside broom · SQL over a database broom fills · one JSON query · a script that broom runs · a library to import. That day the user ruled out the export, the library and SQL, and set that broom holds no model and hands the coding agent facts.

On 2026-11-27 a session in a real Go repo needed every line of each smell. `--json` gave the first five, so it copied broom's linter config and ran the linter itself. One field, `lines`, closed that gap.

---

## The choice

broom answers through its commands, and they grow where a session had to write a script: the script becomes a command, a flag or a field of the JSON, as the rule in AGENTS already says for broom's own work.

---

## Not chosen

- **One JSON query over all the measurements**: Claude would write a query for each question, and a query is a script. That reverses the want "no script to write", and it is a query language for broom to keep.
- **A script that broom runs**: The same, with code from the repo or the session run inside broom.
- **Leave it open**: Each gap would still be closed one way, so the question only kept a TODO.

---

## Consequences

A question broom can't answer shows as a script a session wrote. Each is closed by a command, a flag or a field.

The JSON of a command carries every value its text cuts short, since a cut list is a gap that sends a session to a script.
