# 036. broom keeps its own dependency-cruiser

Decided: 2026-11-19

---

## The problem

dependency-cruiser finds the cycles between folders in TS/JS. It loads the TypeScript beside it and reads no `.ts` file when that one is 7 or later, without a word. A project on TypeScript 7 had the tool installed, the doctor called it ok, and the check read nothing.

---

## The choice

broom installs a copy of its own under its data directory, with a TypeScript 6 beside it, and runs that copy first. It reads a project whatever TypeScript the project uses. The doctor offers it as one command, and one install serves every repo of the machine.

---

## Not chosen

- **Say that the check is off, and offer nothing**: The user set the direction that day: a project broom can't check in full is a project broom doesn't serve.
- **Tell the user to install a TypeScript 6**: In the project it changes their dependencies, and globally it replaces their own TypeScript.
- **Read the imports ourselves, as for Python**: Resolving tsconfig paths, index files and re-exports is what dependency-cruiser exists for.

---

## Consequences

broom installs something outside the project and outside the user's own global tools, still only on a yes. When dependency-cruiser reads with TypeScript 7 itself, the copy is no longer needed.
