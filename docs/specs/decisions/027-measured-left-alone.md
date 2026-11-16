# 027. `tsc` runs without `--incremental`, and jscpd scans the whole repo each time

Decided: 2026-11-16

---

## The problem

Both looked like work done twice.

---

## The choice

Both stay as they are.

---

## Not chosen

- **`tsc --incremental`**: On 800 modules it took 0.75 seconds against 0.81 without, and TypeScript 7 does them in 0.08.
- **A cache for jscpd's scan**: The scan took 2.9 seconds on a 9,279-file repo, once per distinct change.

---

## Consequences

Neither is looked at again until a measurement says otherwise.
