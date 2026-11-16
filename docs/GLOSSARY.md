# Glossary

Each term has its meaning, the words that lost to it and its name in the code where that differs.

| Term | Means | Losing synonyms | In code |
|---|---|---|---|
| Sweep | one run that formats, lints and type-checks a set of files | clean pass | `sweep` |
| Check | the lint, type and smell part of a sweep | gate | `checked`, `gate_files` |
| Finding | one thing a tool reports at a file and line | issue | `Issue` |
| Type error | a compile or type error, which counts anywhere | hard error | `Issue.hard` |
| Smell | code that works and is hard to change, such as a 300-line function | — | `Smell` |
| Sized smell | a smell with a number and two limits | — | `SMELL_LIMITS` |
| Occurrence smell | a smell that counts each time it appears | presence smell | `SMELL_PRESENCE` |
| Soft limit | the size past which a sized smell is a hint | — | `limits[0]` |
| Hard limit | the size past which a sized smell blocks | — | `limits[1]` |
| Hint | a finding Claude is told about without a block at commit | — | `level == "hint"` |
| Block | a finding that stops the commit or the turn's end | denial | `level == "block"` |
| Severe smell | a smell past its hard limit | — | `Issue.severe` |
| Touched smell | an old sized smell in a function, a type or a file the change touches | — | `Smell.touched` |
| Known issue | a finding accepted with a reason, which broom no longer raises | baseline · accepted issue | `baseline.json` |
| Accept | to record a blocked result as known with a reason | — | `broom known --accept` |
| Base | the revision a change is measured against | — | `base` |
| Scratch copy | a temporary copy of the changed files where a tool runs under broom's config | scratch tree | `measure` |
| Real tree | the project's own checkout, where imports resolve | — | `realtree` |
| Hotspot | a file ranked by its smells past the hard limit | — | `hotspots` |
| Turn | the work between one prompt and the moment Claude stops | — | `turns` |
| Legacy | code a repo marks as on its way out, which new code may repeat | — | `legacy` |
| Note | a line that says what a check skipped | — | `notes` |
| Gap | a tool or a config a repo needs and lacks | — | `Item` |
| Session scan | the whole-repo smell scan at session start | — | `session-scan` |
| Ledger | the record of what broom did with each finding | log | `ledger.jsonl` |
| Fix line | the usual fix of one kind of smell, in one sentence | — | `fixes.json` |
| Limits card | the lines that tell Claude a repo's bar at session start | — | `card` |
| Fix | a blocked finding that is gone from a later check that covered it | — | `fix` |
| Pass | a finding that was let through, with how | — | `pass` |
| Self-waiver | a change that loosens the bar: a looser `.broom.json`, a new suppression or a `--no-verify` commit | waiver | `waiver` |
| Turn summary | the one line the user sees when a turn let something through | — | `through_line` |
