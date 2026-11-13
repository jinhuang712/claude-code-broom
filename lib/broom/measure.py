"""Measuring code smells with each language's tool, in a scratch tree, against broom's limits.

Each tool runs alone with a config broom writes, so the project's own configs never apply, and reports what
is past the soft limit as Raw rows: file, line, metric, the function's name (else the line's text), number.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .common import GO_EXTS, JS_EXTS, PY_EXTS, SWIFT_EXTS, resolve_bin, run

Limits = Dict[str, Tuple[int, int]]
TOOL_TIMEOUT = 90
UNREACHABLE = 1_000_000  # a SwiftLint error level nothing reaches: broom tells hints from blocks itself
GO_MOD = "module broomsmells\n\ngo 1.22\n"


@dataclass
class Raw:
    rel: str
    line: int
    metric: str
    key: str  # what matches a finding across versions: the function's name, else the line's text
    value: int
    tool: str


class Reader:
    """Turns one tool's findings in one scratch tree into Raw rows."""

    def __init__(self, root: Path, tool: str, notes: List[str]) -> None:
        self.root, self.tool, self.notes = root, tool, notes
        self.rows: List[Raw] = []

    def json(self, rc: Optional[int], out: str, empty):
        if rc is None:
            self.notes.append(f"timeout:{self.tool} measuring smells")
            return empty
        try:
            return json.loads(out) if out.strip() else empty
        except ValueError:
            self.notes.append(f"{self.tool} failed measuring smells: {out.strip()[:120]}")
            return empty

    def add(self, rel: str, line: int, metric: str, value: Optional[int], name: Optional[str] = None) -> None:
        if value is None:
            return
        rel = self.rel(rel)
        text = self.line_text(rel, line)
        key = name or match(r"\b(?:def|func|function|fn)\s+([A-Za-z_]\w*)", text) or text
        self.rows.append(Raw(rel, line, metric, key, value, self.tool))

    def rel(self, name: str) -> str:
        p = Path(name)
        if not p.is_absolute():
            return name
        try:
            return str(p.resolve().relative_to(self.root.resolve()))
        except ValueError:
            return name

    def line_text(self, rel: str, line: int) -> str:
        try:
            rows = (self.root / rel).read_text(errors="replace").splitlines()
        except OSError:
            return ""
        return rows[line - 1].strip() if 0 < line <= len(rows) else ""


def number(pattern: str, text: str) -> Optional[int]:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def match(pattern: str, text: str) -> Optional[str]:
    m = re.search(pattern, text)
    return m.group(1) if m else None


def quoted_name(text: str) -> Optional[str]:
    return match(r"[`']([^`']+)[`']", text)


# ---------------------------------------------------------------- measures per language


def measure_files(r: Reader, rels: List[str], lim: Limits) -> None:
    for rel in rels:
        count = len((r.root / rel).read_text(errors="replace").splitlines())
        r.add(rel, 1, "file_lines", count if count > lim["file_lines"][0] else None, "file")


def python_functions(r: Reader, rel: str, soft: int) -> None:
    try:
        tree = ast.parse((r.root / rel).read_text(errors="replace"))
    except (SyntaxError, ValueError):
        return

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = prefix
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = f"{prefix}{child.name}."
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                size = (child.end_lineno or child.lineno) - child.lineno + 1
                r.add(rel, child.lineno, "function_lines", size if size > soft else None, inner[:-1])
            walk(child, inner)

    walk(tree, "")


RUFF_METRICS = {"C901": "complexity", "PLR0913": "params", "PLR1702": "nesting"}


def measure_python(r: Reader, rels: List[str], lim: Limits, start: Path) -> None:
    for rel in rels:
        python_functions(r, rel, lim["function_lines"][0])
    ruff = shutil.which("ruff")
    if not ruff:
        r.notes.append("missing:ruff (brew install ruff)")
        return
    cmd = [ruff, "check", "--isolated", "--preview", "--no-fix", "--output-format", "json",
           "--select", ",".join(RUFF_METRICS),
           "--config", f"lint.mccabe.max-complexity={lim['complexity'][0]}",
           "--config", f"lint.pylint.max-args={lim['params'][0]}",
           "--config", f"lint.pylint.max-nested-blocks={lim['nesting'][0]}", *rels]
    rc, out, _ = run(cmd, r.root, timeout=TOOL_TIMEOUT)
    for d in r.json(rc, out, []):
        metric = RUFF_METRICS.get(d.get("code") or "")
        msg = d.get("message", "")
        if metric:
            name = quoted_name(msg) if metric == "complexity" else None
            r.add(d.get("filename", ""), int(d["location"]["row"]), metric, number(r"\((\d+) > \d+\)", msg), name)


OXLINT_METRICS = {"max-lines-per-function": "function_lines", "max-params": "params", "max-depth": "nesting",
                  "complexity": "complexity", "no-nested-ternary": "nested_ternary"}
OXLINT_CATEGORIES = ("correctness", "suspicious", "perf", "pedantic", "style", "restriction", "nursery")


def oxlint_config(lim: Limits) -> dict:
    whole = {"skipBlankLines": False, "skipComments": False}
    return {"plugins": [], "categories": {c: "off" for c in OXLINT_CATEGORIES}, "rules": {
        "max-lines-per-function": ["warn", {"max": lim["function_lines"][0], **whole}],
        "max-params": ["warn", {"max": lim["params"][0]}],
        "max-depth": ["warn", {"max": lim["nesting"][0]}],
        "complexity": ["warn", {"max": lim["complexity"][0]}],
        "no-nested-ternary": "warn",
    }}


def oxlint_value(metric: str, msg: str) -> Optional[int]:
    if metric == "nested_ternary":
        return 1
    return number(r"complexity of (\d+)", msg) if metric == "complexity" else number(r"\((\d+)\)", msg)


def measure_js(r: Reader, rels: List[str], lim: Limits, start: Path) -> None:
    exe = resolve_bin("oxlint", start, start)
    if not exe:
        r.notes.append("missing:oxlint (npm i -g oxlint), so TS/JS smells aren't measured")
        return
    cfg = r.root.parent / f"{r.root.name}-oxlint.json"
    cfg.write_text(json.dumps(oxlint_config(lim)))
    rc, out, _ = run([exe, "-c", str(cfg), "-f", "json", "--no-error-on-unmatched-pattern", *rels], r.root,
                     timeout=TOOL_TIMEOUT)
    for d in r.json(rc, out, {}).get("diagnostics", []):
        rule = re.sub(r"^[\w-]+\(|\)$", "", d.get("code", ""))
        metric = OXLINT_METRICS.get(rule)
        if metric:
            msg = d.get("message", "")
            line = int(((d.get("labels") or [{}])[0].get("span") or {}).get("line", 0))
            r.add(d.get("filename", ""), line, metric, oxlint_value(metric, msg), quoted_name(msg))


def nestif_complexity(depth: int) -> int:
    """nestif scores ifs nested inside an if 1, 2, 3, ... by depth, so `depth` levels score this much."""
    return depth * (depth - 1) // 2


def nesting_depth(complexity: int) -> int:
    return round((1 + (1 + 8 * complexity) ** 0.5) / 2)


def golangci_config(lim: Limits) -> str:
    return "\n".join([
        'version: "2"',
        "linters:",
        "  default: none",
        "  enable: [funlen, nestif, gocognit, revive]",
        "  settings:",
        f"    funlen: {{lines: {lim['function_lines'][0]}, statements: -1, ignore-comments: false}}",
        f"    nestif: {{min-complexity: {nestif_complexity(lim['nesting'][0]) + 1}}}",
        f"    gocognit: {{min-complexity: {lim['complexity'][0] + 1}}}",
        f"    revive: {{rules: [{{name: argument-limit, arguments: [{lim['params'][0]}]}}]}}",
        "run: {tests: true, relative-path-mode: wd}",  # paths from the scratch tree, not the config's directory
        "issues: {max-issues-per-linter: 0, max-same-issues: 0, uniq-by-line: false}",
        "",
    ])


GOLANGCI_READS: Dict[str, Tuple[str, str, Optional[str]]] = {  # linter: metric, value pattern, name pattern
    "funlen": ("function_lines", r"too long \((\d+) >", r"Function '([^']+)'"),
    "gocognit": ("complexity", r"cognitive complexity (\d+)", r"func `([^`]+)`"),
    "nestif": ("nesting", r"\(complexity: (\d+)\)", None),
    "revive": ("params", r"argument-limit: .* but got (\d+)", None),
}


def measure_go(r: Reader, rels: List[str], lim: Limits, start: Path) -> None:
    exe = shutil.which("golangci-lint")
    if not exe:
        r.notes.append("missing:golangci-lint (brew install golangci-lint)")
        return
    (r.root / "go.mod").write_text(GO_MOD)
    cfg = r.root.parent / f"{r.root.name}-golangci.yml"
    cfg.write_text(golangci_config(lim))
    env = {"GOLANGCI_LINT_CACHE": str(r.root.parent / f"{r.root.name}-gocache")}
    rc, out, _ = run([exe, "run", "-c", str(cfg), "--output.json.path", "stdout", "--output.text.path", "stderr",
                      "--show-stats=false", "./..."], r.root, timeout=TOOL_TIMEOUT, env=env)
    for d in (r.json(rc, out, {}) or {}).get("Issues") or []:
        read = GOLANGCI_READS.get(d.get("FromLinter", ""))
        if not read:
            continue
        metric, value_pattern, name_pattern = read
        text, pos = d.get("Text", ""), d.get("Pos") or {}
        value = number(value_pattern, text)
        if metric == "nesting" and value is not None:
            value = nesting_depth(value)
        name = match(name_pattern, text) if name_pattern else None
        r.add(pos.get("Filename", ""), int(pos.get("Line", 0)), metric, value, name)


SWIFTLINT_METRICS = {"function_body_length": "function_lines", "function_parameter_count": "params",
                     "cyclomatic_complexity": "complexity"}


def swiftlint_config(lim: Limits) -> str:
    rows = [f"only_rules: [{', '.join(SWIFTLINT_METRICS)}]"]
    rows += [f"{rule}: {{warning: {lim[metric][0]}, error: {UNREACHABLE}}}" for rule, metric in SWIFTLINT_METRICS.items()]
    return "\n".join(rows) + "\n"


def measure_swift(r: Reader, rels: List[str], lim: Limits, start: Path) -> None:
    exe = shutil.which("swiftlint")
    if not exe:
        r.notes.append("missing:swiftlint (brew install swiftlint)")
        return
    cfg = r.root.parent / f"{r.root.name}-swiftlint.yml"
    cfg.write_text(swiftlint_config(lim))
    rc, out, _ = run([exe, "lint", "--quiet", "--config", str(cfg), "--reporter", "json", *rels], r.root,
                     timeout=TOOL_TIMEOUT)
    for d in r.json(rc, out, []):
        metric = SWIFTLINT_METRICS.get(d.get("rule_id", ""))
        if metric:
            r.add(d.get("file", ""), int(d.get("line") or 0), metric, number(r"(\d+)\D*$", d.get("reason", "")))


MEASURES: List[Tuple[set, Callable[[Reader, List[str], Limits, Path], None]]] = [
    (PY_EXTS, measure_python), (JS_EXTS, measure_js), (GO_EXTS, measure_go), (SWIFT_EXTS, measure_swift),
]
SMELL_EXTS = PY_EXTS | JS_EXTS | GO_EXTS | SWIFT_EXTS


def measure(root: Path, contents: Dict[str, str], lim: Limits, start: Path, notes: List[str]) -> List[Raw]:
    for rel, text in contents.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    reader = Reader(root, "broom", notes)
    measure_files(reader, list(contents), lim)
    for exts, fn in MEASURES:
        rels = [rel for rel in contents if Path(rel).suffix in exts]
        if rels:
            reader.tool = fn.__name__.replace("measure_", "")
            fn(reader, rels, lim, start)
    return reader.rows

