# Contributing

---

## Before you start

A change keeps broom on Python 3.9 with the standard library only. Read [DESIGNS.md](DESIGNS.md) before a change to how broom works, and [PHILOSOPHY.md](PHILOSOPHY.md) before a change to what it does.

---

## Set up

Clone the repo. broom needs `python3` at 3.9 or later and git. The tests skip what needs a tool that isn't installed.

---

## Make a change

Work in a worktree of this repo, commit in small steps and land by fast-forward on the branch the worktree was forked from.

---

## Checks

3 checks must pass:

- `python3 tests/run.py` runs the test suite, each file in a process of its own.
  - It takes about 80 seconds and writes nothing into your own broom data.
  - `python3 -m unittest discover -s tests` runs the same tests one after another.
- `bin/broom smells` must count 0 code smells, and `bin/broom sweep --all --check` must end clean.
- `claude plugin validate .` checks the plugin's manifest and parts.
