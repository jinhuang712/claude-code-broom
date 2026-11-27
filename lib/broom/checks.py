"""Which linters and type checks a set of files needs, and running them in parallel."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from . import ledger, repodata
from .findings import Findings, Issue
from .gitutil import git
from .langlint import check_go, check_python, check_rust, check_swift_build, check_swiftlint
from .state import load_json, update_json
from .toolchain import boundary, css_linters, find_up, js_linters, lang_of, py_root, swift_linter
from .weblint import check_biome, check_eslint, check_oxlint, check_stylelint, check_tsc, ts_projects


Check = Tuple[str, Callable[[], Findings]]  # (key, check); the key lets a check that timed out be skipped later
SLOW_SECONDS = 10  # how long a check that timed out must have run to count as slow


class Plan:
    """The files to check, grouped per project and tool: one run of a tool covers every file of its project."""

    def __init__(self) -> None:
        self.go: Dict[Tuple[Path, Path], List[Path]] = {}
        self.web: Dict[Tuple[str, Path, Path], List[Path]] = {}  # JS/TS and CSS linters; biome and eslint take both
        self.tsc: Set[Tuple[Path, Path]] = set()
        self.rust: Set[Tuple[Path, Path]] = set()
        self.py: Dict[Tuple[Path, Path], List[Path]] = {}
        self.swiftlint: Dict[Tuple[str, Path], List[Path]] = {}
        self.swift: Set[Path] = set()

    def add(self, f: Path) -> None:
        """Put file `f` in the plan under the project and tool for its language; other files are ignored."""
        adders = {"go": self.add_go, "js": self.add_js, "rust": self.add_rust, "py": self.add_py,
                  "css": self.add_css, "swift": self.add_swift}
        lang = lang_of(f)
        if lang in adders:
            adders[lang](f, boundary(f))

    def add_go(self, f: Path, stop: Path) -> None:
        """Add a Go file to the plan under its go.mod's module, found walking up to `stop`; no go.mod means skipped."""
        mod = find_up(f.parent, ["go.mod"], stop)
        if mod:
            self.go.setdefault((mod.parent, stop), []).append(f)

    def add_js(self, f: Path, stop: Path) -> None:
        """Add a JS or TS file to the linters that check it, and to the tsc run of its tsconfig.json when it has one."""
        for tool, d in js_linters(f, stop):
            self.web.setdefault((tool, d, stop), []).append(f)
        if f.suffix.lower() in (".ts", ".tsx", ".mts", ".cts"):
            tsconfig = find_up(f.parent, ["tsconfig.json"], stop)
            if tsconfig:
                self.tsc.update((cfg, stop) for cfg in ts_projects(tsconfig))

    def add_rust(self, f: Path, stop: Path) -> None:
        """Add a Rust file to the clippy run of the crate whose Cargo.toml lies above it, up to `stop`."""
        cargo = find_up(f.parent, ["Cargo.toml"], stop)
        if cargo:
            self.rust.add((cargo.parent, stop))

    def add_py(self, f: Path, stop: Path) -> None:
        """Add a Python file to the ruff run of its project root: the nearest marker up to `stop`, or `stop` itself."""
        self.py.setdefault((py_root(f, stop), stop), []).append(f)

    def add_css(self, f: Path, stop: Path) -> None:
        """Add a CSS file to the linters that check it."""
        for tool, d in css_linters(f, stop):
            self.web.setdefault((tool, d, stop), []).append(f)

    def add_swift(self, f: Path, stop: Path) -> None:
        """Add a Swift file to its swiftlint run, and its package to the build check when it has a Package.swift."""
        self.swiftlint.setdefault(swift_linter(f, stop), []).append(f)
        package = find_up(f.parent, ["Package.swift"], stop)
        if package:  # an Xcode project has no command-line build broom can run
            self.swift.add(package.parent)

    def checks(self, *, whole: bool) -> List[Check]:
        """The planned checks as (name, run) pairs, one per tool and project, for run_checks to time and run."""
        out: List[Check] = [(f"go:{mod}", partial(check_go, mod, fs, stop, whole=whole))
                            for (mod, stop), fs in self.go.items()]
        out += [(f"{tool}:{d}", web_check(tool, d, fs, stop, whole=whole)) for (tool, d, stop), fs in self.web.items()]
        out += [(f"tsc:{cfg}", partial(check_tsc, cfg, stop)) for cfg, stop in self.tsc]
        out += [(f"clippy:{crate}", partial(check_rust, crate, stop)) for crate, stop in self.rust]
        out += [(f"ruff:{root}", partial(check_python, root, fs, whole=whole)) for (root, _stop), fs in self.py.items()]
        out += [(f"{tool}:{d}", partial(check_swiftlint, d, fs, defaults=tool == "swiftlint-default", whole=whole))
                for (tool, d), fs in self.swiftlint.items()]
        out += [(f"swift-build:{package}", partial(check_swift_build, package)) for package in self.swift]
        return out


def web_check(tool: str, d: Path, files: List[Path], stop: Path, *, whole: bool) -> Callable[[], Findings]:
    """The check for one JS/TS or CSS linter in its config directory."""
    if tool in ("oxlint", "oxlint-default"):
        return partial(check_oxlint, d, files, stop, defaults=tool == "oxlint-default", whole=whole)
    if tool in ("stylelint", "stylelint-default"):
        return partial(check_stylelint, d, files, stop, defaults=tool == "stylelint-default")
    if tool == "eslint":
        return partial(check_eslint, d, files, stop, whole=whole)
    return partial(check_biome, d, files, stop, whole=whole)


def plan(files: List[Path], *, whole: bool = False) -> List[Check]:
    """A check per project and tool. With `whole`, each tool checks its whole project instead of the given files."""
    grouped = Plan()
    for f in files:
        grouped.add(f)
    return grouped.checks(whole=whole)


def timed(check: Callable[[], Findings]) -> Tuple[Findings, float]:
    """Run `check` and return its findings with the seconds it took."""
    start = time.monotonic()
    return check(), time.monotonic() - start


def head_of(key: str) -> Optional[str]:
    """The commit HEAD is at in the repo of the directory (or file) a check's `key` names, or None without one."""
    where = Path(key.partition(":")[2] or ".")
    where = where if where.is_dir() else where.parent
    out = git(["rev-parse", "HEAD"], where) if where.is_dir() else None
    return out.strip() if out and out.strip() else None


def where_of(key: str) -> Path:
    """The folder a check's key (`tool:directory`) runs in."""
    return Path(key.partition(":")[2] or "/")


def slow_checks(keys: List[str]) -> Dict[str, str]:
    """The checks of `keys` that ran out of time and whose repo's HEAD hasn't moved since, by the HEAD they ran out of
    time at, from the records of their repos."""
    raw: dict = {}
    for folder in {repodata.at(where_of(k)) for k in keys}:
        data = load_json(folder / repodata.SLOW, {})
        raw.update(data if isinstance(data, dict) else {})
    kept = {k: head for k, head in raw.items() if k in keys and isinstance(head, str)}
    return {k: head for k, head in kept.items() if head_of(k) == head}


def note_slow(ran_out: Dict[str, str]) -> None:
    """Record the checks that ran out of time, each in its repo's record."""
    groups: Dict[Path, Dict[str, str]] = {}
    for k, head in ran_out.items():
        groups.setdefault(repodata.made_at(where_of(k)), {})[k] = head
    for folder, part in groups.items():
        update_json(folder / repodata.SLOW, {}, lambda data, part=part: data.update(part))


def run_checks(files: List[Path], *, remember: bool = False, whole: bool = False) -> Findings:
    """Run every check in parallel. For a hook (`remember`), one that timed out after running for SLOW_SECONDS is
    recorded in its repo's record, for every session and agent, and skipped with a note while its repo's HEAD is the
    commit it ran out of time at, so each one doesn't wait for it again and a new commit gives it another go. One cut
    short because the hook's time ran out before it got far is only late, and runs again."""
    every = plan(files, whole=whole)
    slow = slow_checks([k for k, _ in every]) if remember else {}
    todo = [(k, fn) for k, fn in every if k not in slow]
    notes: List[str] = [f"timeout:{k} skipped until the next commit: it ran out of time at {slow[k][:8]}"
                        for k, _ in every if k in slow]
    issues: List[Issue] = []
    ran_out: Dict[str, str] = {}
    took: Dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, ((found, msgs), seconds) in zip([k for k, _ in todo], pool.map(lambda kv: timed(kv[1]), todo)):
            issues += found
            notes += msgs
            took[key] = seconds
            if seconds >= SLOW_SECONDS and any(m.startswith("timeout:") for m in msgs):
                head = head_of(key)
                if head:
                    ran_out[key] = head
    if remember and ran_out:
        note_slow(ran_out)
    if remember:  # for a hook: the ledger notes how long each check took
        ledger.timed(took)
    return issues, notes
