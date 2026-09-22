"""Linters and type checks per language, run per project with the project's own tools where it has them."""

from __future__ import annotations

import json
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .common import (
    DEFAULTS, GOLANGCI_CFG, PY_ROOT_MARKERS, boundary, find_up, js_linters, lang_of, load_json,
    pkg_scripts_mention, read_jsonc, resolve_bin, run, save_json,
)


@dataclass
class Issue:
    tool: str
    root: Path  # where the check ran, for grouping the report
    file: Path
    line: int
    col: int
    rule: str
    msg: str
    hard: bool = False  # compile/type error: counts outside the changed lines and files


Findings = Tuple[List[Issue], List[str]]


def resolve_in(root: Path, name: str, *fallbacks: Optional[Path]) -> Path:
    p = Path(name)
    if p.is_absolute():
        return p.resolve()
    for base in (root, *fallbacks):
        if base and (base / p).exists():
            return (base / p).resolve()
    return (root / p).resolve()


def targets(files: List[Path], whole: bool) -> List[str]:
    """What to hand a linter: the files, or its whole project (it runs from the project directory)."""
    return ["."] if whole else [str(f) for f in files]


def failure(out: str, err: str) -> str:
    """The first lines explaining why a tool failed; some tools print config errors on stdout."""
    rows = [r.strip(" |x\t") for r in (err.strip() or out.strip()).splitlines()]
    return " / ".join(r for r in rows if r)[:200] or "no output"


# ---------------------------------------------------------------- Go

GOLANGCI_ROW = re.compile(
    r"^(?P<file>[^\s:][^:]*\.go):(?P<line>\d+)(?::(?P<col>\d+))?: (?P<msg>.+?)(?: \((?P<rule>[\w-]+)\))?$"
)
VET_TYPE_ERROR = re.compile(r"^vet: (?P<file>[^:]+\.go):(?P<line>\d+):(?P<col>\d+): (?P<msg>.+)$")


def check_go(module: Path, files: List[Path], stop: Path, whole: bool = False) -> Findings:
    issues: List[Issue] = []
    notes: List[str] = []
    exe = shutil.which("golangci-lint")
    if exe:
        cfg = find_up(module, GOLANGCI_CFG, stop) or DEFAULTS / "golangci.yml"
        pkgs = ["./..."] if whole else sorted({"./" + os.path.relpath(f.parent, module) for f in files})
        rc, out, err = run([
            exe, "run", "-c", str(cfg), "--path-mode=abs", "--output.text.path=stdout",
            "--output.text.print-issued-lines=false", "--output.text.colors=false", "--show-stats=false",
            "--max-issues-per-linter=0", "--max-same-issues=0", "--allow-parallel-runners", *pkgs,
        ], module, timeout=150)
        if rc is None:
            notes.append(f"timeout:golangci-lint in {module}")
        else:
            for row in out.splitlines():
                m = GOLANGCI_ROW.match(row)
                if not m or m["msg"].startswith((": #", "# ")):
                    continue
                rule = m["rule"] or "typecheck"
                issues.append(Issue("golangci-lint", module, resolve_in(module, m["file"]), int(m["line"]),
                                    int(m["col"] or 0), rule, m["msg"], hard=rule == "typecheck"))
            if rc not in (0, 1) and not issues:
                notes.append(f"golangci-lint failed in {module}: {failure(out, err)}")
    else:
        notes.append("missing:golangci-lint (brew install golangci-lint)")

    # Packages nobody touched still have to compile against the ones that changed.
    go = shutil.which("go")
    if go and not whole:  # the whole module was just linted, typecheck included
        edited_dirs = {f.parent for f in files}
        rc, out, err = run([go, "vet", "./..."], module, timeout=150)
        if rc is None:
            notes.append(f"timeout:go vet in {module}")
        for row in (err + out).splitlines():
            m = VET_TYPE_ERROR.match(row)
            if m:
                f = resolve_in(module, m["file"])
                if f.parent not in edited_dirs:
                    issues.append(Issue("go vet", module, f, int(m["line"]), int(m["col"]), "typecheck",
                                        m["msg"], hard=True))
    return issues, notes


# ---------------------------------------------------------------- JS / TS


def check_oxlint(cfg_dir: Path, files: List[Path], stop: Path, defaults: bool, whole: bool = False) -> Findings:
    exe = resolve_bin("oxlint", cfg_dir, stop)
    if not exe:
        return [], ["missing:oxlint (npm i -g oxlint oxlint-tsgolint)"]
    cmd = [exe, "--format", "json", "--no-error-on-unmatched-pattern"]
    if defaults:
        cmd += ["-c", str(DEFAULTS / "oxlintrc.json")]
        type_aware = find_up(cfg_dir, ["tsconfig.json"], stop) is not None
    else:  # a configured project gets type-aware rules only if its own scripts ask for them
        type_aware = pkg_scripts_mention(cfg_dir, "--type-aware") or pkg_scripts_mention(stop, "--type-aware")
    if type_aware and resolve_bin("tsgolint", cfg_dir, stop):
        cmd.append("--type-aware")
    rc, out, err = run(cmd + targets(files, whole), cfg_dir, timeout=90)
    if rc is None:
        return [], [f"timeout:oxlint in {cfg_dir}"]
    try:
        diags = json.loads(out).get("diagnostics", [])
    except ValueError:
        return [], [f"oxlint failed in {cfg_dir}: {failure(out, err)}"]
    issues = []
    for d in diags:
        span = ((d.get("labels") or [{}])[0].get("span") or {})
        issues.append(Issue("oxlint", cfg_dir, resolve_in(cfg_dir, d.get("filename", "")), int(span.get("line", 0)),
                            int(span.get("column", 0)), d.get("code", ""), d.get("message", "")))
    return issues, []


def check_eslint(cfg_dir: Path, files: List[Path], stop: Path, whole: bool = False) -> Findings:
    exe = resolve_bin("eslint", cfg_dir, stop, local_only=True)
    if not exe:
        return [], [f"missing:eslint in {cfg_dir} (install the project's dependencies)"]
    rc, out, err = run([exe, "-f", "json", "--no-warn-ignored", *targets(files, whole)], cfg_dir, timeout=120)
    if rc == 2 and "no-warn-ignored" in err:  # eslintrc-era ESLint
        rc, out, err = run([exe, "-f", "json", *targets(files, whole)], cfg_dir, timeout=120)
    if rc is None:
        return [], [f"timeout:eslint in {cfg_dir}"]
    try:
        results = json.loads(out)
    except ValueError:
        return [], [f"eslint failed in {cfg_dir}: {failure(out, err)}"]
    issues = []
    for r in results:
        for m in r.get("messages", []):
            issues.append(Issue("eslint", cfg_dir, Path(r["filePath"]).resolve(), int(m.get("line") or 0),
                                int(m.get("column") or 0), m.get("ruleId") or "parse", m.get("message", "")))
    return issues, []


def check_biome(cfg_dir: Path, files: List[Path], stop: Path, whole: bool = False) -> Findings:
    exe = resolve_bin("biome", cfg_dir, stop)
    if not exe:
        return [], [f"missing:biome in {cfg_dir} (install the project's dependencies)"]
    rc, out, err = run([exe, "lint", "--reporter=json", *targets(files, whole)], cfg_dir, timeout=90)
    if rc is None:
        return [], [f"timeout:biome in {cfg_dir}"]
    start = out.find("{")
    try:
        diags = json.loads(out[start:]).get("diagnostics", []) if start >= 0 else []
    except ValueError:
        return [], [f"biome failed in {cfg_dir}: {failure(out, err)}"]
    issues = []
    for d in diags:
        loc = d.get("location") or {}
        pos = loc.get("start") or {}
        issues.append(Issue("biome", cfg_dir, resolve_in(cfg_dir, loc.get("path", "")), int(pos.get("line", 0)),
                            int(pos.get("column", 0)), d.get("category", ""), d.get("message", "")))
    return issues, []


TSC_ROW = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\): error (?P<rule>TS\d+): (?P<msg>.*)$")
TSC_GLOBAL = re.compile(r"^error (?P<rule>TS\d+): (?P<msg>.*)$")
# Project-reference bookkeeping ("output file has not been built"), not errors in the code.
TSC_REFERENCE_CODES = {"TS6305", "TS6306", "TS6307", "TS6310"}


def ts_projects(tsconfig: Path) -> List[Path]:
    """The configs tsc should check. A solution-style tsconfig ("files": [] plus references) checks nothing
    itself, so its referenced configs are checked instead."""
    cfg = read_jsonc(tsconfig)
    refs = cfg.get("references") or []
    if not (refs and cfg.get("files") == [] and not cfg.get("include")):
        return [tsconfig]
    out = []
    for r in refs:
        p = (tsconfig.parent / str(r.get("path", ""))).resolve()
        p = p / "tsconfig.json" if p.is_dir() else p
        if p.is_file():
            out.append(p)
    return out


def check_tsc(config: Path, stop: Path) -> Findings:
    project = config.parent
    exe = resolve_bin("tsc", project, stop)
    if not exe:
        return [], ["missing:tsc (npm i -g typescript)"]
    # --composite false: check a referenced project on its own, the way electron-vite's typecheck scripts do.
    rc, out, err = run([exe, "--noEmit", "--pretty", "false", "--composite", "false", "-p", str(config)], project,
                       timeout=150)
    if rc is None:
        return [], [f"timeout:tsc in {project}"]
    issues = []
    for row in (out + err).splitlines():
        m = TSC_ROW.match(row)
        g = TSC_GLOBAL.match(row) if not m else None
        if m and m["rule"] not in TSC_REFERENCE_CODES:
            issues.append(Issue("tsc", project, resolve_in(project, m["file"]), int(m["line"]), int(m["col"]),
                                m["rule"], m["msg"], hard=True))
        elif g and g["rule"] not in TSC_REFERENCE_CODES:
            issues.append(Issue("tsc", project, config, 0, 0, g["rule"], g["msg"], hard=True))
    return issues, []


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


def check_python(root: Path, files: List[Path], whole: bool = False) -> Findings:
    ruff = shutil.which("ruff")
    if not ruff:
        return [], ["missing:ruff (brew install ruff)"]
    rc, out, err = run([ruff, "check", "--output-format", "concise", "--no-fix", "--force-exclude",
                        *targets(files, whole)], root, timeout=60)
    if rc is None:
        return [], [f"timeout:ruff in {root}"]
    issues = []
    for row in out.splitlines():
        m = RUFF_ROW.match(row)
        if m:
            issues.append(Issue("ruff", root, resolve_in(root, m["file"]), int(m["line"]), int(m["col"]), m["rule"],
                                re.sub(r"^\[\*\] ", "", m["msg"])))
    return issues, []


# ---------------------------------------------------------------- planning


def plan(files: List[Path], whole: bool = False) -> List[Tuple[str, Callable[[], Findings]]]:
    """(key, check) per project and tool; the key lets a check that timed out be skipped later. With `whole`,
    each tool checks its whole project instead of the given files."""
    go: Dict[Tuple[Path, Path], List[Path]] = {}
    js: Dict[Tuple[str, Path, Path], List[Path]] = {}
    tsc: Set[Tuple[Path, Path]] = set()
    rust: Set[Tuple[Path, Path]] = set()
    py: Dict[Tuple[Path, Path], List[Path]] = {}
    for f in files:
        stop = boundary(f)
        lang = lang_of(f)
        if lang == "go":
            mod = find_up(f.parent, ["go.mod"], stop)
            if mod:
                go.setdefault((mod.parent, stop), []).append(f)
        elif lang == "js":
            for tool, d in js_linters(f, stop):
                js.setdefault((tool, d, stop), []).append(f)
            if f.suffix.lower() in (".ts", ".tsx", ".mts", ".cts"):
                tsconfig = find_up(f.parent, ["tsconfig.json"], stop)
                if tsconfig:
                    tsc.update((cfg, stop) for cfg in ts_projects(tsconfig))
        elif lang == "rust":
            cargo = find_up(f.parent, ["Cargo.toml"], stop)
            if cargo:
                rust.add((cargo.parent, stop))
        elif lang == "py":
            marker = find_up(f.parent, PY_ROOT_MARKERS, stop)
            py.setdefault((marker.parent if marker else stop, stop), []).append(f)

    checks: List[Tuple[str, Callable[[], Findings]]] = []
    for (mod, stop), fs in go.items():
        checks.append((f"go:{mod}", partial(check_go, mod, fs, stop, whole)))
    for (tool, d, stop), fs in js.items():
        if tool in ("oxlint", "oxlint-default"):
            fn = partial(check_oxlint, d, fs, stop, tool == "oxlint-default", whole)
        elif tool == "eslint":
            fn = partial(check_eslint, d, fs, stop, whole)
        else:
            fn = partial(check_biome, d, fs, stop, whole)
        checks.append((f"{tool}:{d}", fn))
    for cfg, stop in tsc:
        checks.append((f"tsc:{cfg}", partial(check_tsc, cfg, stop)))
    for crate, stop in rust:
        checks.append((f"clippy:{crate}", partial(check_rust, crate, stop)))
    for (root, _stop), fs in py.items():
        checks.append((f"ruff:{root}", partial(check_python, root, fs, whole)))
    return checks


def run_checks(files: List[Path], slow_path: Optional[Path] = None, whole: bool = False) -> Findings:
    """Run every check in parallel; a check that times out is recorded in `slow_path` and skipped after."""
    slow = set(load_json(slow_path, [])) if slow_path else set()
    todo = [(k, fn) for k, fn in plan(files, whole) if k not in slow]
    issues: List[Issue] = []
    notes: List[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, (found, msgs) in zip([k for k, _ in todo], pool.map(lambda kv: kv[1](), todo)):
            issues += found
            notes += msgs
            if any(m.startswith("timeout:") for m in msgs):
                slow.add(key)
    if slow_path:
        save_json(slow_path, sorted(slow))
    return issues, notes
