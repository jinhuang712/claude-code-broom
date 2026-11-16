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
| Sticky finding | a type error or a severe smell, which never passes on a retry alone | — | `sticky` |
| Known issue | a finding broom let through and no longer raises | baseline · accepted issue | `baseline.json` |
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
