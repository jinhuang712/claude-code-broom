"""Which linters and type checks a set of files needs, and running them in parallel."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .findings import Findings, Issue
from .langlint import check_go, check_python, check_rust, check_swift_build, check_swiftlint
from .state import load_json, save_json
from .toolchain import PY_ROOT_MARKERS, boundary, css_linters, find_up, js_linters, lang_of, swift_linter
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
        adders = {"go": self.add_go, "js": self.add_js, "rust": self.add_rust, "py": self.add_py,
                  "css": self.add_css, "swift": self.add_swift}
        lang = lang_of(f)
        if lang in adders:
            adders[lang](f, boundary(f))

    def add_go(self, f: Path, stop: Path) -> None:
        mod = find_up(f.parent, ["go.mod"], stop)
        if mod:
            self.go.setdefault((mod.parent, stop), []).append(f)

    def add_js(self, f: Path, stop: Path) -> None:
        for tool, d in js_linters(f, stop):
            self.web.setdefault((tool, d, stop), []).append(f)
        if f.suffix.lower() in (".ts", ".tsx", ".mts", ".cts"):
            tsconfig = find_up(f.parent, ["tsconfig.json"], stop)
            if tsconfig:
                self.tsc.update((cfg, stop) for cfg in ts_projects(tsconfig))

    def add_rust(self, f: Path, stop: Path) -> None:
        cargo = find_up(f.parent, ["Cargo.toml"], stop)
        if cargo:
            self.rust.add((cargo.parent, stop))

    def add_py(self, f: Path, stop: Path) -> None:
        marker = find_up(f.parent, PY_ROOT_MARKERS, stop)
        self.py.setdefault((marker.parent if marker else stop, stop), []).append(f)

    def add_css(self, f: Path, stop: Path) -> None:
        for tool, d in css_linters(f, stop):
            self.web.setdefault((tool, d, stop), []).append(f)

    def add_swift(self, f: Path, stop: Path) -> None:
        self.swiftlint.setdefault(swift_linter(f, stop), []).append(f)
        package = find_up(f.parent, ["Package.swift"], stop)
        if package:  # an Xcode project has no command-line build broom can run
            self.swift.add(package.parent)

    def checks(self, *, whole: bool) -> List[Check]:
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
    start = time.monotonic()
    return check(), time.monotonic() - start


def run_checks(files: List[Path], slow_path: Optional[Path] = None, *, whole: bool = False) -> Findings:
    """Run every check in parallel; one that timed out after running for SLOW_SECONDS is recorded in `slow_path`
    and skipped after. One cut short because the hook's time ran out before it got far is only late: it runs again."""
    slow = set(load_json(slow_path, [])) if slow_path else set()
    todo = [(k, fn) for k, fn in plan(files, whole=whole) if k not in slow]
    issues: List[Issue] = []
    notes: List[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, ((found, msgs), seconds) in zip([k for k, _ in todo], pool.map(lambda kv: timed(kv[1]), todo)):
            issues += found
            notes += msgs
            if seconds >= SLOW_SECONDS and any(m.startswith("timeout:") for m in msgs):
                slow.add(key)
    if slow_path:
        save_json(slow_path, sorted(slow))
    return issues, notes
