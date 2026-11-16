# 024. A hook's tools are kept to a quarter of the cores, not lowered in priority

Decided: 2026-11-16

---

## The problem

A check took every core. Next to a busy foreground job, that job kept 73 to 82 percent of its speed.

---

## The choice

Each tool a hook starts is kept to a quarter of the cores through `GOMAXPROCS`, `RAYON_NUM_THREADS` and `CARGO_BUILD_JOBS`, unless the user set them.

---

## Not chosen

- **`nice 10`**: It changed nothing.
- **macOS's background class**: It made the check 3.6 times slower.

---

## Consequences

The check took 11.8 seconds instead of 9.7, and the foreground job kept 97 to 104 percent of its speed.
