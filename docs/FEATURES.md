# Features

The marks: ✅ built · 🚧 built, with a gap named beside it · ❔ claimed and not yet run, with the reason beside it · ⬜ planned.

A ✅ here means the test suite covers the feature and passed on 2026-11-18.

---

## Summary

```
Features
├── ✅ F1: Setup — a repo gets the tools and configs it needs
│   ├── ✅ F1.1: Doctor — what a repo needs and has
│   ├── ✅ F1.2: Offer at session start — Claude offers a setup when a repo has gaps
│   ├── ❔ F1.3: /broom:setup — a skill, not run in this pass
│   ├── ✅ F1.4: Default configs — added where a project has none
│   └── ⬜ F1.5: Protection list — which checks run and which don't
├── ✅ F2: Sweep — Claude's changes are formatted, checked and held back
│   ├── ✅ F2.1: Commit check — a git commit is formatted, checked and held back
│   ├── ✅ F2.2: Turn-end check — what a turn changed is checked when Claude stops
│   ├── ✅ F2.3: Subagent check — a subagent fixes its own work
│   ├── ✅ F2.4: git's pre-commit hook — commits Claude Code never sees
│   │   └── ✅ F2.4.1: Offered at setup
│   ├── ✅ F2.5: Known issues — what was let through, and why
│   │   ├── ✅ F2.5.1: A reason for every pass
│   │   └── ✅ F2.5.2: A turn can end with a finding open
│   ├── ✅ F2.6: Sweep on request — a scope in the user's own words
│   ├── 🚧 F2.7: Time limit — a cold build can be cut off and go unchecked
│   ├── 🚧 F2.8: Self-waivers shown — a config loosened by a command is missed with `check_on` at `commit`
│   └── ✅ F2.9: Messages that say how to fix — the fix beside the finding
├── ✅ F3: Formatting — the project's formatter on what changed
│   ├── ✅ F3.1: When to format — at commit, after every edit, or never
│   └── ✅ F3.2: How much to format — the scope
│       ├── ✅ F3.2.1: changed
│       ├── ✅ F3.2.2: function
│       └── ✅ F3.2.3: file
├── ✅ F4: Smells — one bar for code that is hard to change
│   ├── ✅ F4.1: Sized smells — a hint past the soft limit, a block past the hard one
│   ├── ✅ F4.2: Occurrence smells — a change that adds one gets its level
│   │   ├── 🚧 F4.2.1: Broad catch — Python only
│   │   ├── ✅ F4.2.2: Skipped test
│   │   └── 🚧 F4.2.3: Untested file — paired by file name only
│   ├── ✅ F4.3: Duplicate code — a new copy anywhere in the repo
│   ├── ✅ F4.4: Dead code — code a change adds and nothing uses
│   ├── 🚧 F4.5: Cycles — Go, Swift and Rust aren't read
│   │   ├── ✅ F4.5.1: Import cycle
│   │   └── 🚧 F4.5.2: Folder cycle — TS/JS needs a TypeScript below 7
│   ├── ✅ F4.6: What is skipped — dependencies, build output and generated code
│   ├── ✅ F4.7: Tests — measured by rules of their own
│   ├── ✅ F4.8: Limits told before the work — Claude knows the bar when it starts
│   └── 🚧 F4.9: Old smells in touched code — outside Python only lengths are told
├── ✅ F5: Cleanup — the smells already in a repo
│   ├── ✅ F5.1: Ranking — the smells of a repo or an area, worst first
│   ├── ✅ F5.2: Session note — Claude raises severe smells at a natural point
│   └── ❔ F5.3: /broom:clean — a skill, not run in this pass
├── ❔ F6: Language servers — the docs say checked in Claude Code 2.1.280 and 2.1.283, not run in this pass
│   └── ❔ F6.1: Diagnostics as Claude edits — six servers
├── ✅ F7: Settings — defaults that are never asked
│   ├── ✅ F7.1: User settings — four choices in /config
│   └── ✅ F7.2: Per-repo file — .broom.json
│       ├── ✅ F7.2.1: exclude
│       ├── ✅ F7.2.2: legacy
│       ├── ✅ F7.2.3: limits and test_limits
│       └── ✅ F7.2.4: smells_off
├── 🚧 F8: Languages — six, with uneven smell coverage
│   ├── ✅ F8.1: Go
│   ├── ✅ F8.2: TS/JS
│   ├── 🚧 F8.3: Rust — 16 of the smells, and nesting only hints
│   ├── ✅ F8.4: Python
│   ├── 🚧 F8.5: CSS, SCSS and Less — file length and duplicates only
│   └── 🚧 F8.6: Swift — no compile check for Xcode projects
├── 🚧 F9: Record — tiers by fix rate are not built
│   ├── ✅ F9.1: Ledger — every block, fix, pass and skip leaves a line
│   ├── 🚧 F9.2: Turn summary — not shown with `check_on` at `commit`
│   ├── ✅ F9.3: Report — the record of a repo over a period
│   └── ⬜ F9.4: Tiers by fix rate — a rule nobody fixes stops interrupting
├── 🚧 F10: Diagnosis — a repo's numbers before and after a refactor
│   ├── ✅ F10.1: Whole-repo diagnosis — an old repo's smells in full, as a report and as data
│   ├── ✅ F10.2: Hotspots by churn — the files that are both bad and often changed
│   ├── 🚧 F10.3: Before and after — a tool that fails silently in the base's checkout is not caught
│   ├── 🚧 F10.4: Numbers on request — a test is paired with its code by file name
│   └── ✅ F10.5: Claude knows what to ask — broom before a script
└── 🚧 F11: Check-up — Swift is left out of dependencies and deprecated APIs
    ├── ✅ F11.1: Counters — numbers that speak only when they grow
    ├── 🚧 F11.2: Test coverage — files are listed and functions are not
    ├── ✅ F11.3: Duplicate tests — tests that repeat one another
    ├── ✅ F11.4: Dead code in the whole repo — what nothing uses any more
    ├── 🚧 F11.5: Missing comments — in TS/JS only exported functions and classes
    ├── 🚧 F11.6: Dependencies — Rust's tool was never run here
    └── 🚧 F11.7: Deprecated APIs — Swift is not covered, and TS/JS needs tsgolint
```

---

## Groups

11 groups:

- [F1: Setup](features/F1-setup.md)
- [F2: Sweep](features/F2-sweep.md)
- [F3: Formatting](features/F3-formatting.md)
- [F4: Smells](features/F4-smells.md)
- [F5: Cleanup](features/F5-cleanup.md)
- [F6: Language servers](features/F6-language-servers.md)
- [F7: Settings](features/F7-settings.md)
- [F8: Languages](features/F8-languages.md)
- [F9: Record](features/F9-record.md)
- [F10: Diagnosis](features/F10-diagnosis.md)
- [F11: Check-up](features/F11-checkup.md)

---

## Not planned

7 things the project will not build:

- **Running tests**: They are too slow for a commit check, and CI runs them. broom reads a coverage report and doesn't make one.
- **Replacing pre-commit, lefthook or CI**: broom looks after Claude's work and leaves the user's own commits and CI to them.
- **A linter or a formatter of its own**: broom runs existing ones.
- **A style**: Defaults exist only where a project has none.
- **Layering rules without a project's own**: Layers differ per project, and none of the author's repos declares any.
- **A compile check for Xcode projects**: It needs `xcodebuild`, a scheme and minutes.
- **A build server for Xcode projects**: A tool such as xcode-build-server does that, and broom doesn't set one up.
