# Hook limits

This part bounds what one hook run may take: time, cores and waiting. It exists because a hook that runs long makes the session feel stuck.

```
0 s ── hook starts, the clock starts
       every command gets what is left of 25 s and a quarter of the cores
20 s ─ still running: write hook-trace.log
25 s ─ commands are killed with everything they started
28 s ─ the hook gives up and lets the commit, edit or stop through
30 s ─ Claude Code's timeout for the hook
```

---

## Time

`hooks.json` gives every hook a 30-second timeout, the async ones too. The commands a run starts share 25 seconds. A tool is cut off with everything it started, not left compiling in the background. The check then goes ahead without it and says so in a note.

A commit or a stop that a tool kept from finishing is never blocked for it, and the content isn't recorded as passed. At 28 seconds the hook gives up for what no command's timeout reaches.

A check that ran out of time after 10 seconds is skipped for 20 minutes in every session, with a note. A session scan that ran out of time keeps what it counted as a floor and runs again at the next session start.

- [026: A hook run is cut at 30 seconds](decisions/026-thirty-second-hook.md)

---

## Cores

Each tool a hook starts is kept to a quarter of the cores through `GOMAXPROCS`, `RAYON_NUM_THREADS` and `CARGO_BUILD_JOBS`, unless the user set them.

- [024: Tools are kept to a quarter of the cores](decisions/024-thread-caps.md)

---

## Waiting

A command writes to files, not pipes, and reads no input. A tool that exits leaving a daemon behind is not waited for. git is told not to start its file system monitor, take its optional index lock or ask for a password.

The input Claude Code sends is read until it parses, not until its pipe closes. A lock on a state file is waited for 5 seconds at most.

A hook still running after 20 seconds writes `hook-trace.log` in the data directory: where each thread is, and which processes it started and hasn't heard from.

- [025: A command writes to files](decisions/025-files-not-pipes.md)

---

## Shared state

Many hooks run at once. Each read, change and write of the passed record, the known issues, the last blocked commit, the notes, the setup answers and the measurement cache holds a lock, and no hook puts back what another changed meanwhile.

---

## Work done once

git is asked once per repo for what is tracked and what differs, not once per file. One `git status` gives HEAD and the changed files. The repo of a directory and the main checkout of a worktree are found without a process.

A hook loads only what its event needs. The command line, the linters and the commit gate are loaded when there is code to check, so an edit or a turn's end with nothing to do costs little more than the start of Python.

golangci-lint gets a results cache per module path. The shared cache matches packages by content and replays the file paths it stored, which hands a worktree another directory's findings. Caches of golangci-lint and clippy unused for 7 days are removed.

A hook's own failure never blocks: a broken check lets the commit, the edit or the stop through.

- [027: Measured and left as it was](decisions/027-measured-left-alone.md)
