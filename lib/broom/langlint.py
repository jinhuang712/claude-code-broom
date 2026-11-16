"""Linters and builds for Go, Rust, Python and Swift, run with the project's own tools where it has them."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import List, Optional, Tuple

from .findings import Findings, Issue, failure, resolve_in, targets
from .gitutil import run
from .state import DATA_ROOT, DEFAULTS, prune_dirs, short_hash
from .toolchain import GOLANGCI_CFG, find_up


# ---------------------------------------------------------------- Go

VET_TYPE_ERROR = re.compile(r"^vet: (?P<file>[^:]+\.go):(?P<line>\d+):(?P<col>\d+): (?P<msg>.+)$")
GOLANGCI_CACHES = DATA_ROOT / "golangci"


def golangci_cache(module: Path) -> Path:
    """A golangci-lint results cache for this module's path alone. The shared one matches packages by content and
    replays the paths it stored, so a worktree, or a copy since deleted, hands broom another directory's files
    and every issue is dropped as not in the commit. Caches unused for 7 days go: each worktree of an agent has a
    path of its own, so they pile up."""
    d = GOLANGCI_CACHES / short_hash(str(module))
    d.mkdir(parents=True, exist_ok=True)
    os.utime(d)
    prune_dirs(GOLANGCI_CACHES, 7)
    return d


def _golangci(module: Path, files: List[Path], stop: Path, *, whole: bool) -> Findings:
    exe = shutil.which("golangci-lint")
    if not exe:
        return [], ["missing:golangci-lint (brew install golangci-lint)"]
    cfg = find_up(module, GOLANGCI_CFG, stop) or DEFAULTS / "golangci.yml"
    pkgs = ["./..."] if whole else sorted({"./" + os.path.relpath(f.parent, module) for f in files})
    rc, out, err = run([
        exe, "run", "-c", str(cfg), "--path-mode=abs", "--output.json.path=stdout", "--output.text.path=stderr",
        "--show-stats=false", "--max-issues-per-linter=0", "--max-same-issues=0", "--allow-parallel-runners", *pkgs,
    ], module, timeout=150, env={"GOLANGCI_LINT_CACHE": str(golangci_cache(module))})
    if rc is None:
        return [], [f"timeout:golangci-lint in {module}"]
    issues = golangci_issues(module, out)
    notes = []
    if rc not in (0, 1) and not issues:
        notes.append(f"golangci-lint failed in {module}: {failure(out, err)}")
    return issues, notes


def golangci_issues(module: Path, out: str) -> List[Issue]:
    """golangci-lint's findings, from its JSON report: a compile error comes as the linter `typecheck`."""
    try:
        found = (json.loads(out) if out.strip() else {}).get("Issues") or []
    except (ValueError, AttributeError):
        return []
    issues = []
    for d in found:
        pos, rule = d.get("Pos") or {}, d.get("FromLinter") or "typecheck"
        if pos.get("Filename") and pos.get("Line"):
            issues.append(Issue("golangci-lint", module, resolve_in(module, pos["Filename"]), int(pos["Line"]),
                                int(pos.get("Column") or 0), rule, d.get("Text", ""), hard=rule == "typecheck"))
    return issues


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

def clippy_issues(crate: Path, out: str, workspace: Optional[Path], stop: Path) -> List[Issue]:
    """clippy's warnings and errors, from the JSON messages cargo prints: those with a place in a file."""
    issues = []
    for row in out.splitlines():
        try:
            message = json.loads(row).get("message")
        except (ValueError, AttributeError):
            continue
        span = next((sp for sp in (message or {}).get("spans") or [] if sp.get("is_primary")), None)
        level = (message or {}).get("level")
        if span and level in ("error", "warning"):
            f = resolve_in(crate, span["file_name"], workspace.parent if workspace else None, stop)
            issues.append(Issue("clippy", crate, f, int(span["line_start"]), int(span["column_start"]),
                                (message.get("code") or {}).get("code") or level, message.get("message", ""),
                                hard=level == "error"))
    return issues


def check_rust(crate: Path, stop: Path) -> Findings:
    cargo = shutil.which("cargo")
    if not cargo:
        return [], ["missing:cargo"]
    rc, out, _ = run([cargo, "clippy", "--message-format=json", "--quiet"], crate, timeout=120)
    if rc is None:
        return [], [f"timeout:cargo clippy in {crate} (a cold build?)"]
    return clippy_issues(crate, out, find_up(crate.parent, ["Cargo.toml"], stop), stop), []


def ruff_issues(root: Path, out: str) -> List[Issue]:
    """ruff's findings, from its JSON report; a syntax error has no rule code."""
    try:
        found = json.loads(out) if out.strip() else []
    except ValueError:
        return []
    return [Issue("ruff", root, resolve_in(root, d["filename"]), int(d["location"]["row"]),
                  int(d["location"]["column"]), d.get("code") or "syntax-error", d.get("message", ""))
            for d in found if isinstance(d, dict) and d.get("filename") and d.get("location")]


def check_python(root: Path, files: List[Path], *, whole: bool = False) -> Findings:
    ruff = shutil.which("ruff")
    if not ruff:
        return [], ["missing:ruff (brew install ruff)"]
    rc, out, err = run([ruff, "check", "--output-format", "json", "--no-fix", "--force-exclude",
                        *targets(files, whole=whole)], root, timeout=60)
    if rc is None:
        return [], [f"timeout:ruff in {root}"]
    issues = ruff_issues(root, out)
    return issues, ([f"ruff failed in {root}: {failure(out, err)}"] if rc not in (0, 1) and not issues else [])


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
# Swift 6.4's build system words a failure of its own as `error: <file>:<line>:<col> <message>`.
SWIFT_BUILD_ERROR = re.compile(r"^error: (?P<file>/.+?\.swift):(?P<line>\d+):(?P<col>\d+) (?P<msg>.+)$")
# macOS's Command Line Tools have neither test framework, where Xcode has both (checked in 26.6 and 6.4).
NO_TEST_FRAMEWORK = re.compile(r"^(no such module|unable to resolve module dependency:) '(XCTest|Testing)'$")


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def swift_build(swift: str, package: Path, args: List[str], timeout: float) -> Tuple[Optional[int], str, str]:
    """`swift build` with its output as plain text: Swift 6.4 colors its diagnostics even into a pipe, which
    leaves escape codes between `:` and `error:`, where the patterns below look for them."""
    rc, out, err = run([swift, "build", *args], package, timeout=timeout)
    return rc, ANSI.sub("", out), ANSI.sub("", err)


def swift_errors(package: Path, out: str) -> List[Issue]:
    issues = []
    for row in out.splitlines():
        m = SWIFT_ERROR.match(row) or SWIFT_BUILD_ERROR.match(row)
        if m:
            issues.append(Issue("swift build", package, Path(m["file"]).resolve(), int(m["line"]), int(m["col"]),
                                m.groupdict().get("group") or "error", m["msg"], hard=True))
    return issues


def check_swift_build(package: Path) -> Findings:
    """`swift build --build-tests`, in the package's own .build, which the project's builds share. Errors only:
    SwiftPM prints warnings just for the files it recompiles, so they'd come and go between runs. The language
    server shows Claude the warnings as it edits."""
    swift = shutil.which("swift")
    if not swift:
        return [], ["missing:swift (install Xcode or the Swift toolchain)"]
    deadline = time.monotonic() + 150
    rc, out, err = swift_build(swift, package, ["--build-tests"], 150)
    notes: List[str] = []
    issues = swift_errors(package, out + err) if rc is not None else []
    if any(NO_TEST_FRAMEWORK.match(i.msg) for i in issues):  # the tests can't be built here, the sources can
        notes.append(f"swift build in {package} left the tests out: this toolchain has no XCTest or swift-testing "
                     "(the Command Line Tools without Xcode?)")
        rc, out, err = swift_build(swift, package, [], max(deadline - time.monotonic(), 10))
        issues = swift_errors(package, out + err) if rc is not None else []
    if rc is None:
        return [], [*notes, f"timeout:swift build in {package} (a cold build?)"]
    if rc != 0 and not issues:  # dependency resolution, the manifest's toolchain, a link step: not a line of code
        notes.append(f"swift build failed in {package}: {failure(out, err)}")
    return issues, notes
