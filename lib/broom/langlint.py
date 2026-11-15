"""Linters and builds for Go, Rust, Python and Swift, run with the project's own tools where it has them."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import List

from .findings import Findings, Issue, failure, resolve_in, targets
from .gitutil import run
from .state import DATA_ROOT, DEFAULTS, prune_dirs, short_hash
from .toolchain import GOLANGCI_CFG, find_up


# ---------------------------------------------------------------- Go

GOLANGCI_ROW = re.compile(
    r"^(?P<file>[^\s:][^:]*\.go):(?P<line>\d+)(?::(?P<col>\d+))?: (?P<msg>.+?)(?: \((?P<rule>[\w-]+)\))?$"
)
VET_TYPE_ERROR = re.compile(r"^vet: (?P<file>[^:]+\.go):(?P<line>\d+):(?P<col>\d+): (?P<msg>.+)$")
GOLANGCI_CACHES = DATA_ROOT / "golangci"


def golangci_cache(module: Path) -> Path:
    """A golangci-lint results cache for this module's path alone. The shared one matches packages by content and
    replays the paths it stored, so a worktree, or a copy since deleted, hands broom another directory's files
    and every issue is dropped as not in the commit. Caches unused for 30 days go."""
    d = GOLANGCI_CACHES / short_hash(str(module))
    d.mkdir(parents=True, exist_ok=True)
    os.utime(d)
    prune_dirs(GOLANGCI_CACHES, 30)
    return d


def _golangci(module: Path, files: List[Path], stop: Path, *, whole: bool) -> Findings:
    exe = shutil.which("golangci-lint")
    if not exe:
        return [], ["missing:golangci-lint (brew install golangci-lint)"]
    cfg = find_up(module, GOLANGCI_CFG, stop) or DEFAULTS / "golangci.yml"
    pkgs = ["./..."] if whole else sorted({"./" + os.path.relpath(f.parent, module) for f in files})
    rc, out, err = run([
        exe, "run", "-c", str(cfg), "--path-mode=abs", "--output.text.path=stdout",
        "--output.text.print-issued-lines=false", "--output.text.colors=false", "--show-stats=false",
        "--max-issues-per-linter=0", "--max-same-issues=0", "--allow-parallel-runners", *pkgs,
    ], module, timeout=150, env={"GOLANGCI_LINT_CACHE": str(golangci_cache(module))})
    if rc is None:
        return [], [f"timeout:golangci-lint in {module}"]
    issues: List[Issue] = []
    for row in out.splitlines():
        m = GOLANGCI_ROW.match(row)
        if not m or m["msg"].startswith((": #", "# ")):
            continue
        rule = m["rule"] or "typecheck"
        issues.append(Issue("golangci-lint", module, resolve_in(module, m["file"]), int(m["line"]),
                            int(m["col"] or 0), rule, m["msg"], hard=rule == "typecheck"))
    notes = []
    if rc not in (0, 1) and not issues:
        notes.append(f"golangci-lint failed in {module}: {failure(out, err)}")
    return issues, notes


def _vet(module: Path, files: List[Path]) -> Findings:
    """Packages nobody touched still have to compile against the ones that changed."""
    go = shutil.which("go")
    if not go:
        return [], []
    edited_dirs = {f.parent for f in files}
    rc, out, err = run([go, "vet", "./..."], module, timeout=150)
    if rc is None:
        return [], [f"timeout:go vet in {module}"]
    issues = []
    for row in (err + out).splitlines():
        m = VET_TYPE_ERROR.match(row)
        if m:
            f = resolve_in(module, m["file"])
            if f.parent not in edited_dirs:
                issues.append(Issue("go vet", module, f, int(m["line"]), int(m["col"]), "typecheck", m["msg"],
                                    hard=True))
    return issues, []


def check_go(module: Path, files: List[Path], stop: Path, *, whole: bool = False) -> Findings:
    issues, notes = _golangci(module, files, stop, whole=whole)
    if whole:  # the whole module was just linted, typecheck included
        return issues, notes
    vetted, vet_notes = _vet(module, files)
    return issues + vetted, notes + vet_notes


# ---------------------------------------------------------------- Rust / Python

CLIPPY_ROW = re.compile(
    r"^(?P<file>[^\s:][^:]*\.rs):(?P<line>\d+):(?P<col>\d+): (?P<level>error|warning)(?:\[(?P<code>[^\]]+)\])?: (?P<msg>.*)$"
)


def check_rust(crate: Path, stop: Path) -> Findings:
    cargo = shutil.which("cargo")
    if not cargo:
        return [], ["missing:cargo"]
    rc, out, err = run([cargo, "clippy", "--message-format=short", "--quiet"], crate, timeout=120)
    if rc is None:
        return [], [f"timeout:cargo clippy in {crate} (cold build? it is skipped for the rest of this session)"]
    workspace = find_up(crate.parent, ["Cargo.toml"], stop)
    issues = []
    for row in (err + out).splitlines():
        m = CLIPPY_ROW.match(row)
        if m:
            f = resolve_in(crate, m["file"], workspace.parent if workspace else None, stop)
            issues.append(Issue("clippy", crate, f, int(m["line"]), int(m["col"]), m["code"] or m["level"],
                                m["msg"], hard=m["level"] == "error"))
    return issues, []


RUFF_ROW = re.compile(r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+): (?P<rule>[\w-]+):? (?P<msg>.*)$")


def check_python(root: Path, files: List[Path], *, whole: bool = False) -> Findings:
    ruff = shutil.which("ruff")
    if not ruff:
        return [], ["missing:ruff (brew install ruff)"]
    rc, out, err = run([ruff, "check", "--output-format", "concise", "--no-fix", "--force-exclude",
                        *targets(files, whole=whole)], root, timeout=60)
    if rc is None:
        return [], [f"timeout:ruff in {root}"]
    issues = []
    for row in out.splitlines():
        m = RUFF_ROW.match(row)
        if m:
            issues.append(Issue("ruff", root, resolve_in(root, m["file"]), int(m["line"]), int(m["col"]), m["rule"],
                                re.sub(r"^\[\*\] ", "", m["msg"])))
    return issues, []


# ---------------------------------------------------------------- Swift

# Dependencies and build output: CocoaPods and Carthage checkouts are sometimes committed. On the command line, for
# the same reason as stylelint's: SwiftLint reads `excluded` relative to the config, which for broom's is the plugin.
SWIFT_VENDORED = {"Pods", "Carthage", ".build", "DerivedData"}


def swift_vendored(f: Path, root: Path) -> bool:
    try:
        parts = f.relative_to(root).parts
    except ValueError:
        parts = f.parts
    return bool(SWIFT_VENDORED & set(parts[:-1]))


def check_swiftlint(cfg_dir: Path, files: List[Path], *, defaults: bool, whole: bool = False) -> Findings:
    exe = shutil.which("swiftlint")
    if not exe:
        return [], ["missing:swiftlint (brew install swiftlint)"]
    cmd = [exe, "lint", "--reporter", "json", "--quiet"]
    if defaults:  # the files themselves, even for a whole-project sweep: a directory would take in vendored code
        cmd += ["--config", str(DEFAULTS / "swiftlint.yml")]
        paths = [str(f) for f in files if not swift_vendored(f, cfg_dir)]
        if not paths:
            return [], []
    else:  # the project's `excluded` holds even for files named on the command line
        cmd.append("--force-exclude")
        paths = targets(files, whole=whole)
    rc, out, err = run(cmd + paths, cfg_dir, timeout=90)
    if rc is None:
        return [], [f"timeout:swiftlint in {cfg_dir}"]
    if rc == 1 and "No lintable files found" in err:  # the project's config excludes all of them
        return [], []
    try:
        results = json.loads(out)
    except ValueError:
        return [], [f"swiftlint failed in {cfg_dir}: {failure(out, err)}"]
    issues = []
    for r in results if isinstance(results, list) else []:
        issues.append(Issue("swiftlint", cfg_dir, Path(r.get("file") or "").resolve(), int(r.get("line") or 0),
                            int(r.get("character") or 0), r.get("rule_id", ""), r.get("reason", "")))
    return issues, []


# SwiftPM prints absolute paths. Swift 6.1 and later append the diagnostic group: `[#DeprecatedDeclaration]`.
SWIFT_ERROR = re.compile(
    r"^(?P<file>/.+?\.swift):(?P<line>\d+):(?P<col>\d+): error: (?P<msg>.+?)(?: \[#(?P<group>[\w-]+)\])?$"
)
# macOS's Command Line Tools have neither test framework, where Xcode has both (checked in 26.6).
NO_TEST_FRAMEWORK = re.compile(r"^no such module '(XCTest|Testing)'$")


def swift_errors(package: Path, out: str) -> List[Issue]:
    issues = []
    for row in out.splitlines():
        m = SWIFT_ERROR.match(row)
        if m:
            issues.append(Issue("swift build", package, Path(m["file"]).resolve(), int(m["line"]), int(m["col"]),
                                m["group"] or "error", m["msg"], hard=True))
    return issues


def check_swift_build(package: Path) -> Findings:
    """`swift build --build-tests`, in the package's own .build, which the project's builds share. Errors only:
    SwiftPM prints warnings just for the files it recompiles, so they'd come and go between runs. The language
    server shows Claude the warnings as it edits."""
    swift = shutil.which("swift")
    if not swift:
        return [], ["missing:swift (install Xcode or the Swift toolchain)"]
    deadline = time.monotonic() + 150
    rc, out, err = run([swift, "build", "--build-tests"], package, timeout=150)
    notes: List[str] = []
    issues = swift_errors(package, out + err) if rc is not None else []
    if any(NO_TEST_FRAMEWORK.match(i.msg) for i in issues):  # the tests can't be built here, the sources can
        notes.append(f"swift build in {package} left the tests out: this toolchain has no XCTest or swift-testing "
                     "(the Command Line Tools without Xcode?)")
        rc, out, err = run([swift, "build"], package, timeout=max(deadline - time.monotonic(), 10))
        issues = swift_errors(package, out + err) if rc is not None else []
    if rc is None:
        return [], [*notes, f"timeout:swift build in {package} (cold build? it is skipped for the rest of this "
                            "session)"]
    if rc != 0 and not issues:  # dependency resolution, the manifest's toolchain, a link step: not a line of code
        notes.append(f"swift build failed in {package}: {failure(out, err)}")
    return issues, notes
