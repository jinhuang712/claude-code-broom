# AGENTS.md

This file holds what an agent cannot learn by reading the code: how the work on broom goes.

**Read again after a compaction.** When the window is new or was compacted, read the what-we-build skill and every guide in full if it is installed, then every doc in the read order, before anything else.

---

## Tags

A list of tagged lines holds one family, and the sentence before it says which.

| Family | Tag | Means |
|---|---|---|
| Definition | `[YES]` | what a thing is or holds |
| Definition | `[NO]` | what it is not or leaves out |
| Rule | `[MUST]` | required |
| Rule | `[NEVER]` | forbidden |
| Rule | `[BETTER]` | preferred, not required |

---

## Read order

11 docs:

1. [AGENTS.md](AGENTS.md) holds the rules of the work.
2. [PROPOSAL.md](docs/PROPOSAL.md) holds why broom exists and what it wants.
3. [PHILOSOPHY.md](docs/PHILOSOPHY.md) holds the stances broom takes.
4. [DESIGNS.md](docs/DESIGNS.md) holds the commitments every design must meet.
5. [GOALS.md](docs/plan/GOALS.md) holds what is checked and the last result.
6. [FEATURES.md](docs/FEATURES.md) holds what broom does and will do.
7. [ROADMAP.md](docs/plan/ROADMAP.md) holds what comes next.
8. [ISSUES.md](docs/plan/ISSUES.md) holds agreed work that adds no capability.
9. [TODO.md](docs/plan/TODO.md) holds the open questions.
10. [GLOSSARY.md](docs/GLOSSARY.md) holds the terms.
11. [ARCHITECTURE.md](docs/specs/ARCHITECTURE.md) holds the map of the parts.

The other docs are read when the work needs them.

---

## Layout

9 facts:

- The root holds 3 files: `README.md` · `AGENTS.md` · `CHANGELOG.md`.
- `.claude/CLAUDE.md` only loads this file.
- [assets/](assets/) holds the README's hero and its two flow pictures, each in a dark and a light version, the broom logo in black and in white, and the card GitHub shows when the repo is shared.
- [docs/](docs/) holds the reasons and the contract: PROPOSAL · PHILOSOPHY · DESIGNS · FEATURES · CLI · INSTALL · GLOSSARY · CONTRIBUTING.
- [docs/features/](docs/features/) holds one file per feature group.
- [docs/specs/](docs/specs/) holds how each part works, with [docs/specs/decisions/](docs/specs/decisions/) under it.
- [docs/plan/](docs/plan/) holds 4 docs: GOALS · ROADMAP · ISSUES · TODO.
- `report/` holds work records and the ratchet's numbers, and git ignores it through `.git/info/exclude`.
- `docs/README.zh-CN.md` is the Chinese copy of README and changes with it.

---

## While you work

The handbook is [CONTRIBUTING.md](docs/CONTRIBUTING.md): how to set up, run the checks and land a change.

20 rules:

- [MUST] follow these rules strictly unless the user rejects one.
- [MUST] read every doc you work on in full.
- [MUST] work in a worktree inside this repo.
- [MUST] land a worktree on the branch it was forked from by fast-forward.
- [MUST] run the checks in CONTRIBUTING before a change lands.
- [MUST] look at each checkpoint's end for kinds of rot broom still misses, then add each to FEATURES or to TODO.
- [MUST] push and tag when a checkpoint or a sub-checkpoint ends and the checks pass, then tell the user.
- [MUST] publish a GitHub release for every tag, with its CHANGELOG section as the notes.
- [MUST] bump Z for a release, and Y when a whole checkpoint ends.
- [MUST] update the installed plugin after a release, then tell the user to reload.
- [MUST] keep this repo at zero findings by broom's own measure.
- [MUST] turn a script written to count or check something in a repo into a broom command, or into a TODO item.
- [MUST] measure this repo with broom when a stage ends, and record the gain against the baseline in `report/ratchet/`.
- [NEVER] give a doc to a subagent to read or write.
- [NEVER] use a script or a search in place of reading a doc in full.
- [NEVER] check the goals for a small change.
- [NEVER] bump X.
- [NEVER] force a push.
- [NEVER] write the name of another repo of the user, a file in it or a usage number from it into a tracked file.
- [BETTER] give code work to a subagent with a short brief, then read its diff before it lands.

Work meets 14 cases. Follow every branch that applies, since several can hold at once:

```
What is happening?
├── The user stops you
│   └── stop at once, with all your agents
├── A doc and something disagree
│   ├── The user says something a doc contradicts
│   │   └── say so before you act
│   └── You find a contradiction
│       ├── tell the user
│       └── pick no side
├── You are about to change something
│   ├── read the doc that owns it first
│   └── The work needs the code
│       └── a subagent may read it
├── You change something
│   ├── check what you touched against the rules
│   ├── You make a choice the DECISIONS guide counts as one
│   │   └── write it down at once
│   ├── You change a fact or a rule
│   │   └── search the docs for what it now contradicts
│   ├── Something in the update tree below happens
│   │   └── update the docs it names in the same change
│   └── The change lands
│       └── before you report, fix what it left behind in the docs and `TODO.md`
├── A piece of work ends
│   ├── The work at hand is done and nothing is next
│   │   └── go through `TODO.md` with the user
│   └── A checkpoint ends or a release is near
│       ├── check the goals it names
│       └── A checkpoint ends
│           └── run the skill's start pass if it is installed
└── Other developers build on the project
    ├── say it may need a wiki
    └── let the user pick its form
```

Read only the docs the work needs.

```
What do you read?
├── Your window is new or was compacted
│   └── read again as the rule at the top says, then every doc in the read order
├── You need to know where things stand
│   └── scan ROADMAP · ISSUES · TODO · GOALS
├── You are about to change something
│   └── What does it change?
│       ├── Why the project exists or how it thinks
│       │   ├── its reason, its wants or who it is for           PROPOSAL
│       │   ├── a stance that steers the whole project           PHILOSOPHY
│       │   └── a commitment the design must meet                DESIGNS
│       ├── What it does, and when
│       │   ├── what the user sees or does                       FEATURES
│       │   ├── a command, its output or an exit code            CLI
│       │   ├── an effect with a test or a number                GOALS
│       │   ├── when it comes or how far along it is             ROADMAP
│       │   ├── agreed work that adds no capability              ISSUES
│       │   ├── a question nobody has answered                   TODO
│       │   └── what shipped in a release                        CHANGELOG
│       ├── How it is built
│       │   ├── how the parts fit                                specs/ARCHITECTURE
│       │   ├── how a part works inside                          specs/
│       │   └── a choice between ways                            specs/decisions/
│       └── How it is used and kept
│           ├── what a visitor reads first                       README
│           ├── how to install it                                INSTALL
│           ├── how to set up, run the checks or send a change   CONTRIBUTING
│           ├── a term of the project                            GLOSSARY
│           └── a rule for how the work is done                  AGENTS
└── A doc and something disagree
    └── read the doc that owns the fact and the thing that disagrees with it
```

Update only the docs an event affects.

```
What just happened?
├── A requirement was agreed
│   ├── FEATURES           what it does
│   ├── ROADMAP            when it comes
│   └── GOALS              the effect it must have
├── Other work was agreed
│   ├── ISSUES             what it is and why
│   └── ROADMAP            when it comes
├── A change was done
│   ├── CHANGELOG          what shipped
│   ├── FEATURES           its status
│   ├── ROADMAP            its progress
│   ├── ISSUES             without the issue it did
│   ├── specs/             how the part works now
│   ├── ARCHITECTURE       how the parts fit now
│   ├── CLI                how it is called now
│   └── README, INSTALL    how it is used now
├── A decision was made       decisions/
├── A question stayed open    TODO
├── A todo was done           delete it from TODO
├── A number moved            GOALS
├── A commitment changed      DESIGNS
└── A new term appeared       GLOSSARY
```

---

## Exceptions

The user rejected 4 rules of the what-we-build skill on 2026-11-17, for details only:

- "let the user decide" does not hold for a detail.
- "show the user every change before you commit it" does not hold.
- "take agreement on a direction as approval of a change" is allowed.
- "settle or write down anything before you have talked it through" is allowed for a detail.

The agent narrowed 1 rule on 2026-11-17 under that delegation:

- "give a doc to a subagent to read" is allowed as the brief for code work. A subagent still never writes a doc and never decides from one.

---

## How we work

The user gives the direction, and the agent settles the details and reports afterwards. A direction is a new want, a new stance or a thing broom refuses to become. A direction still goes to the user first.
