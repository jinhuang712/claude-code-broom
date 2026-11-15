"""JS/TS and CSS linters and the TypeScript type check, run with the project's own tools where it has them."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

from .findings import Findings, Issue, failure, resolve_in, targets
from .gitutil import run
from .state import DEFAULTS, read_jsonc
from .toolchain import DIALECT_DEFAULTS, find_up, in_node_modules, pkg_scripts_mention, resolve_bin


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


# ---------------------------------------------------------------- CSS

# Build output and minified files, as in oxlint's defaults. On the command line: stylelint reads `ignoreFiles`
# relative to the config's own directory, which for broom's defaults is the plugin, not the project.
STYLELINT_DEFAULT_IGNORES = ("**/dist/**", "**/build/**", "**/out/**", "**/coverage/**", "**/*.min.css")


def check_stylelint(cfg_dir: Path, files: List[Path], stop: Path, defaults: bool) -> Findings:
    """stylelint on the files themselves, even for a whole-project sweep: a glob would also hand broom's defaults
    the files of packages that have a config of their own."""
    exe = resolve_bin("stylelint", cfg_dir, stop)
    if not exe:
        if defaults:
            return [], ["missing:stylelint (npm i -D stylelint in the project)"]
        return [], [f"missing:stylelint in {cfg_dir} (install the project's dependencies)"]
    notes: List[str] = []
    cmd = [exe, "-f", "json", "--allow-empty-input"]
    if defaults:
        cmd += ["-c", str(DEFAULTS / "stylelintrc.yml")]
        for pattern in STYLELINT_DEFAULT_IGNORES:
            cmd += ["--ignore-pattern", pattern]
        # stylelint loads the SCSS and Less configs from the project, the way it loads a project's own plugins.
        for ext, (dialect, pkg) in DIALECT_DEFAULTS.items():
            if any(f.suffix.lower() == ext for f in files) and not in_node_modules(pkg, cfg_dir, stop):
                files = [f for f in files if f.suffix.lower() != ext]
                notes.append(f"missing:{pkg} (npm i -D {pkg} in the project, for {dialect})")
    if not files:
        return [], notes
    rc, out, err = run(cmd + [str(f) for f in files], cfg_dir, timeout=90)
    if rc is None:
        return [], notes + [f"timeout:stylelint in {cfg_dir}"]
    # stylelint 16+ reports on stderr, older ones on stdout.
    results = None
    for stream in (out, err):
        start = stream.find("[")
        try:
            results = json.JSONDecoder().raw_decode(stream[start:])[0] if start >= 0 else None
        except ValueError:
            continue
        if isinstance(results, list):
            break
    if not isinstance(results, list):
        return [], notes + [f"stylelint failed in {cfg_dir}: {failure(out, err)}"]
    issues = []
    for r in results:
        for w in r.get("warnings", []):
            rule = w.get("rule", "")
            msg = re.sub(rf"\s*\({re.escape(rule)}\)$", "", w.get("text", "")) if rule else w.get("text", "")
            issues.append(Issue("stylelint", cfg_dir, Path(r.get("source", "")).resolve(), int(w.get("line") or 0),
                                int(w.get("column") or 0), rule, msg))
        notes += [f"stylelint config in {cfg_dir}: {w.get('text', '')}" for w in r.get("invalidOptionWarnings", [])]
    return issues, list(dict.fromkeys(notes))
