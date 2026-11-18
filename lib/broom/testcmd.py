"""Whether a Bash command runs a project's tests, judged by its words. broom never runs a test: it only looks.

The command is split the way the shell splits it (gitcmd), so a word in quotes or in a here-document is no command:
`git commit -m "run pytest"` and `echo npm test` run no test, and `cd x && pytest` does, since any part of a command
counts. A runner is named by its own words (the tables below). A repo adds more in .broom.json `test_commands`: a part
of a command that starts with one of those word sequences is a test run.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import List, Optional, Sequence

from .gitcmd import ASSIGNMENT, WRAPPERS, split_commands, without_heredocs, without_redirections

RUNNERS = {"pytest", "py.test", "tox", "nox", "jest", "vitest", "mocha"}  # the program alone runs tests
SUBCOMMANDS = {  # programs that run tests with one of these subcommands
    "go": {"test"}, "cargo": {"test", "nextest"}, "swift": {"test"}, "npm": {"test", "t", "tst"},
    "pnpm": {"test", "t"}, "yarn": {"test"}, "bun": {"test"},
}
SCRIPT_RUNNERS = {"npm", "pnpm", "yarn", "bun"}  # `<manager> run test:unit` runs the package's test script
RUN_WORDS = {"run", "run-script"}
TEST_TARGETS = {  # programs that run tests when one of their words names the target
    "make": {"test", "tests"}, "gmake": {"test", "tests"}, "xcodebuild": {"test", "test-without-building"},
}
TEST_MODULES = {"pytest", "unittest", "tox", "nox"}  # `python -m pytest`
INTERPRETER = re.compile(r"python[\d.]*|node|bun|ruby|perl|php|bash|sh|zsh|dash")
SHELLS = {"sh", "bash", "zsh", "dash"}
WRAPPING = {**dict.fromkeys(WRAPPERS, 1), "env": 1, "exec": 1, "timeout": 2}  # words before the program, and how many
LAUNCHERS = {  # programs that run another program, which is the one that counts
    ("uv", "run"), ("uvx",), ("poetry", "run"), ("pipenv", "run"), ("pdm", "run"), ("hatch", "run"), ("rye", "run"),
    ("npx",), ("pnpx",), ("bunx",), ("pnpm", "exec"), ("pnpm", "dlx"), ("yarn", "exec"), ("yarn", "dlx"), ("bun", "x"),
}
VALUE_FLAGS = {"--filter", "-F", "-C", "--prefix", "--dir", "-w", "--workspace", "--cwd", "-p", "--package"}
SCRIPT_EXTENSIONS = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".php"}
RUNNER_NAME = re.compile(r"(?:run[-_]?)?(?:all[-_]?)?tests?(?:[-_]?(?:all|suite|runner))?")  # run_tests, test, tests
FOLDER_RUNNERS = {"run", "runner", "main", "all", "run_all", "run-all", "runall"}  # a runner's name in a tests folder
UNDER_TESTS = re.compile(r"(^|/)(tests?|__tests__|Tests)/")
MAX_NESTING = 2  # `bash -c 'bash -c "pytest"'`: how deep a command inside a command is read


def parts(command: str) -> List[List[str]]:
    """The words of each command in the line. A line the shell reading can't follow (a quote that never closes) is read
    as plain words, quotes and all, so that a test run in it is still seen."""
    try:
        found = split_commands(without_heredocs(command))
    except ValueError:
        found = [[w.strip("'\"") for w in row.split()] for row in re.split(r"[;&|()\n]+", command)]
    return [words for words in (without_redirections(p) for p in found) if words]


def unwrapped(words: Sequence[str]) -> List[str]:
    """The words without what stands before the program: variables set for it (`CI=1`) and wrappers (`time`, `env`,
    `timeout 60`)."""
    out = list(words)
    while out:
        drop = 1 if ASSIGNMENT.match(out[0]) else WRAPPING.get(out[0])
        if not drop:
            break
        out = out[drop:]
    return out


def launched(words: Sequence[str]) -> List[str]:
    """The program a launcher runs, with its words (`uv run pytest -q` is `pytest -q`), after any wrappers; the words
    as they are when no launcher stands first."""
    out = unwrapped(words)
    for size in (2, 1):
        if tuple(out[:size]) in LAUNCHERS:
            rest = out[size:]
            while rest and rest[0].startswith("-"):
                rest = rest[1:]
            return launched(rest)
    return out


def after_flags(words: Sequence[str]) -> List[str]:
    """The words from the first that is no option, no toolchain (`cargo +nightly test`) and no value of an option that
    takes one (`pnpm --filter web test`)."""
    i = 0
    while i < len(words) and words[i].startswith(("-", "+")):
        i += 2 if words[i] in VALUE_FLAGS else 1
    return list(words[i:])


def runs_subcommand(prog: str, rest: Sequence[str]) -> bool:
    """Whether `prog` with the words `rest` runs tests by a subcommand: `go test`, `cargo nextest`, `npm test`,
    `pnpm run test:unit`."""
    sub = after_flags(rest)
    if not sub:
        return False
    if sub[0] in SUBCOMMANDS.get(prog, ()):
        return True
    script = after_flags(sub[1:])
    return prog in SCRIPT_RUNNERS and sub[0] in RUN_WORDS and bool(script) and script[0].startswith("test")


def runner_script(path: str) -> bool:
    """Whether `path` is a script that runs a project's tests: named like a runner (`run_tests.sh`, `test.sh`, wherever it
    is), or a runner or a test file in a tests folder (`tests/run.py`, `tests/test_a.py`)."""
    name = Path(path)
    stem = name.stem.lower()
    if name.suffix not in SCRIPT_EXTENSIONS:
        return False
    if RUNNER_NAME.fullmatch(stem):
        return True
    return bool(UNDER_TESTS.search(path)) and (stem in FOLDER_RUNNERS or stem.startswith("test_") or stem.endswith("_test"))


def runs_script(prog: str, words: Sequence[str]) -> bool:
    """Whether an interpreter runs a test script: `python3 tests/run.py`, `bash run_tests.sh`; or a script is run by its
    path (`./tests/run.sh`, `script/test`)."""
    if INTERPRETER.fullmatch(prog):
        return any(runner_script(w) for w in words[1:] if not w.startswith("-"))
    path = words[0]
    if "/" not in path or path.endswith("/"):
        return False
    return runner_script(path) or (not Path(path).suffix and bool(RUNNER_NAME.fullmatch(Path(path).name.lower())))


def runs_module(words: Sequence[str]) -> bool:
    """Whether `-m` names a test runner among the words: `python -m pytest`, `coverage run -m unittest`."""
    return any(a == "-m" and b in TEST_MODULES for a, b in zip(words, words[1:]))


def shell_script(words: Sequence[str]) -> Optional[str]:
    """What `bash -c '<script>'` runs: the script, or None when `words` are no shell with -c (`-lc` and `-ec` count)."""
    if Path(words[0]).name not in SHELLS:
        return None
    for i, word in enumerate(words[1:], 1):
        if word.startswith("-") and not word.startswith("--") and word.endswith("c"):
            return words[i + 1] if i + 1 < len(words) else None
    return None


def started_with(words: Sequence[str], spec: object) -> bool:
    """Whether the `words` of a command start with the word sequence in `spec`, a string such as `just check`, as it is
    or after the launcher and wrappers of each."""
    try:
        seq = shlex.split(spec) if isinstance(spec, str) else []
    except ValueError:
        return False
    if not seq:
        return False
    bare_seq = launched(seq)
    return list(words[:len(seq)]) == seq or bool(bare_seq) and launched(words)[:len(bare_seq)] == bare_seq


def part_runs_tests(words: Sequence[str], custom: object, depth: int) -> bool:
    """Whether one command, as its words, runs tests: by a runner of the tables, by a script or by the repo's own
    `custom` word sequences; a shell given a script with -c is read into, `depth` levels deep."""
    plain = unwrapped(words)
    if not plain:
        return False
    if isinstance(custom, list) and any(started_with(plain, spec) for spec in custom):
        return True
    words = launched(plain)
    if not words:
        return False
    script = shell_script(words)
    if script is not None:
        return depth < MAX_NESTING and is_test_run(script, custom, depth=depth + 1)
    prog = Path(words[0]).name
    if prog in RUNNERS or runs_subcommand(prog, words[1:]) or runs_script(prog, words):
        return True
    return bool(TEST_TARGETS.get(prog, set()) & set(words[1:])) or (
        (INTERPRETER.fullmatch(prog) is not None or prog == "coverage") and runs_module(words))


def is_test_run(command: str, custom: object = None, *, depth: int = 0) -> bool:
    """Whether the Bash `command` runs tests: any one of its parts does. `custom` is the repo's .broom.json
    `test_commands`, a list of strings; anything else is none."""
    return any(part_runs_tests(words, custom, depth) for words in parts(command))
