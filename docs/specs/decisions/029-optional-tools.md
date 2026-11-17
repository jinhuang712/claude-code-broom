# 029. A tool broom can do without is listed and never asked for

Decided: 2026-11-17

---

## The problem

Some checks need a tool few repos have: knip, deptry and cargo-machete for unused packages, osv-scanner for vulnerabilities, tsgolint for deprecated calls in TS/JS. A missing tool is a gap, and a gap makes Claude offer a setup in every session until the user answers.

---

## The choice

These tools are optional. `broom doctor` lists them after the gaps with what each finds and its install command. They are no gap: nothing offers them at session start, and they change neither the repo's health nor an exit code. A hook never shows the note that one is missing. `broom diagnose` and `broom smells` show it, since their counts would otherwise read as cleaner than the code is.

---

## Not chosen

- **A gap like any other tool**: Every repo with a `package.json` would be asked to install three more tools for checks that run only in a diagnosis.
- **A note once per session**: It nags in every TS/JS repo for a tool the user never asked about.
- **Silence everywhere**: A diagnosis that says nothing reads as "none found".

---

## Consequences

A user learns of an optional tool only from `broom doctor` or a diagnosis. The check-up leaves a counter out when its optional tool is missing, so installing the tool later doesn't read as growth.
