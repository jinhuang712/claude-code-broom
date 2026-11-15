"""Measuring code smells with each language's tool, in a scratch tree, against broom's limits.

Each tool runs alone with a config broom writes, so the project's own configs never apply, and reports what
is past the soft limit as Raw rows: file, line, metric, the function's name (else the line's text), number.
"""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .config import SMELL_PRESENCE
from .gitutil import run
from .jsmeasure import measure_js
from .reading import TOOL_TIMEOUT, Limits, Raw, Reader, match, number, quoted_name
from .toolchain import CSS_EXTS, GO_EXTS, JS_EXTS, PY_EXTS, RS_EXTS, SWIFT_EXTS

UNREACHABLE = 1_000_000  # a SwiftLint error level nothing reaches: broom tells hints from blocks itself
GO_MOD = "module broomsmells\n\ngo 1.22\n"


# ---------------------------------------------------------------- measures per language


def measure_files(r: Reader, rels: List[str], lim: Limits) -> None:
    for rel in rels:
        count = len((r.root / rel).read_text(errors="replace").splitlines())
        r.add(rel, 1, "file_lines", count if count > lim["file_lines"][0] else None, "file")


# A line that starts an import; one that opens a bracket runs on to the line that closes it.
JS_IMPORT = re.compile(r"import[\s{*'\"]|export\s+(\*|\{|type\s*\{)|(const|let|var)\s+[\w{},:\s]+=\s*require\(")
IMPORT_START = {
    **{ext: re.compile(r"import\s+[\w.]|from\s+[\w.]+\s+import\b") for ext in PY_EXTS},
    **{ext: JS_IMPORT for ext in JS_EXTS},
    **{ext: re.compile(r"import\b") for ext in GO_EXTS},
    **{ext: re.compile(r"(@testable\s+)?import\s") for ext in SWIFT_EXTS},
}


def code_lines(rel: str, text: str) -> int:
    """The file's lines besides its imports, for telling a longer file from longer imports."""
    rows = text.splitlines()
    start = IMPORT_START.get(Path(rel).suffix)
    if start is None:
        return len(rows)
    imports = depth = 0
    for row in rows:
        s = row.strip()
        if depth or start.match(s):
            imports += 1
            depth = max(0, depth + s.count("(") + s.count("{") - s.count(")") - s.count("}"))
    return len(rows) - imports


def nested_ternaries(r: Reader, rel: str, tree: ast.AST) -> None:
    """A conditional expression inside another one's test, value or alternative; ruff has no rule for it."""
    for node in ast.walk(tree):
        if isinstance(node, ast.IfExp):
            for part in (node.test, node.body, node.orelse):
                if isinstance(part, ast.IfExp):
                    r.add(rel, part.lineno, "nested_ternary", 1)


def python_sizes(r: Reader, rel: str, lim: Limits) -> None:
    """Function and class lengths from Python's own parser, which ruff doesn't measure in lines, and its nested
    conditional expressions."""
    try:
        tree = ast.parse((r.root / rel).read_text(errors="replace"))
    except (SyntaxError, ValueError):
        return
    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                walk(child, prefix)
                continue
            metric = "type_lines" if isinstance(child, ast.ClassDef) else "function_lines"
            size = (child.end_lineno or child.lineno) - child.lineno + 1
            r.add(rel, child.lineno, metric, size if size > lim[metric][0] else None, prefix + child.name)
            walk(child, f"{prefix}{child.name}.")

    walk(tree, "")
    nested_ternaries(r, rel, tree)


RUFF_METRICS = {
    "C901": "complexity", "PLR0913": "params", "PLR1702": "nesting",
    "PGH003": "suppression", "PGH004": "suppression", "S110": "swallowed_error", "ERA001": "commented_code",
    "PLR2004": "magic_numbers", "T201": "debug_output", "T203": "debug_output", "ANN401": "type_escape",
    "PLW0603": "globals", "FBT001": "bool_params", "PT011": "broad_test_asserts",
    **{f"ARG00{n}": "unused_params" for n in range(1, 6)}, **{f"FIX00{n}": "todo" for n in range(1, 5)},
}


def measure_python(r: Reader, rels: List[str], lim: Limits, _start: Path) -> None:
    for rel in rels:
        python_sizes(r, rel, lim)
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
            value = 1 if metric in SMELL_PRESENCE else number(r"\((\d+) > \d+\)", msg)
            r.add(d.get("filename", ""), int(d["location"]["row"]), metric, value, name)


def nestif_complexity(depth: int) -> int:
    """nestif scores ifs nested inside an if 1, 2, 3, ... by depth, so `depth` levels score this much."""
    return depth * (depth - 1) // 2


def nesting_depth(complexity: int) -> int:
    return round((1 + (1 + 8 * complexity) ** 0.5) / 2)


def golangci_config(lim: Limits) -> str:
    """Linters that read syntax alone: the scratch tree holds only the changed files, so imports don't resolve,
    and one linter that needs types (goconst, forbidigo, gochecknoglobals) would stop them all."""
    revive = [f"{{name: argument-limit, arguments: [{lim['params'][0]}]}}", "{name: unused-parameter}",
              "{name: empty-block}", "{name: flag-parameter}", "{name: unchecked-type-assertion}"]
    return "\n".join([
        'version: "2"',
        "linters:",
        "  default: none",
        "  enable: [funlen, nestif, gocognit, revive, mnd, nolintlint, godox]",
        "  settings:",
        f"    funlen: {{lines: {lim['function_lines'][0]}, statements: -1, ignore-comments: false}}",
        f"    nestif: {{min-complexity: {nestif_complexity(lim['nesting'][0]) + 1}}}",
        f"    gocognit: {{min-complexity: {lim['complexity'][0] + 1}}}",
        f"    revive: {{rules: [{', '.join(revive)}]}}",
        "    nolintlint: {require-explanation: true, require-specific: true}",
        "    godox: {keywords: [TODO, FIXME, HACK, XXX]}",
        "run: {tests: true, relative-path-mode: wd}",  # paths from the scratch tree, not the config's directory
        "issues: {max-issues-per-linter: 0, max-same-issues: 0, uniq-by-line: false}",
        "",
    ])


# linter, the text it starts with, metric, value pattern (none: an occurrence), name pattern
GOLANGCI_READS: List[Tuple[str, str, str, Optional[str], Optional[str]]] = [
    ("funlen", "", "function_lines", r"too long \((\d+) >", r"Function '([^']+)'"),
    ("gocognit", "", "complexity", r"cognitive complexity (\d+)", r"func `([^`]+)`"),
    ("nestif", "", "nesting", r"\(complexity: (\d+)\)", None),
    ("revive", "argument-limit", "params", r"but got (\d+)", None),
    ("revive", "unused-parameter", "unused_params", None, None),
    ("revive", "empty-block", "swallowed_error", None, None),
    ("revive", "flag-parameter", "bool_params", None, None),
    ("revive", "unchecked-type-assertion", "type_escape", None, None),
    ("mnd", "", "magic_numbers", None, None),
    ("nolintlint", "", "suppression", None, None),
    ("godox", "", "todo", None, None),
]


def golangci_read(linter: str, text: str) -> Optional[Tuple[str, Optional[int], Optional[str]]]:
    """The metric, value and name a golangci-lint finding stands for, or None for one broom doesn't measure."""
    for name, start, metric, value_pattern, name_pattern in GOLANGCI_READS:
        if name == linter and text.startswith(start):
            value = number(value_pattern, text) if value_pattern else 1
            if metric == "nesting" and value is not None:
                value = nesting_depth(value)
            return metric, value, match(name_pattern, text) if name_pattern else None
    return None


def measure_go(r: Reader, _rels: List[str], lim: Limits, _start: Path) -> None:
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
        read = golangci_read(d.get("FromLinter", ""), d.get("Text", ""))
        if read:
            pos = d.get("Pos") or {}
            r.add(pos.get("Filename", ""), int(pos.get("Line", 0)), *read)


SWIFTLINT_SIZES = {"function_body_length": "function_lines", "function_parameter_count": "params",
                   "cyclomatic_complexity": "complexity", "type_body_length": "type_lines"}
SWIFTLINT_METRICS = {
    **SWIFTLINT_SIZES, "blanket_disable_command": "suppression", "no_empty_block": "swallowed_error",
    "unused_parameter": "unused_params", "no_magic_numbers": "magic_numbers", "todo": "todo",
    "force_cast": "type_escape", "force_unwrapping": "type_escape", "force_try": "type_escape",
}


# SwiftLint custom rules of broom's own, for what it has no rule for: what a regex on the source can see.
SWIFT_CUSTOM_RULES = {
    # The name must not follow a dot or a word character: `printer.print(` is a method, not the global function.
    "debug_output": {"regex": r"(?<![\w.])(print|debugPrint|NSLog|dump)\(", "match_kinds": ["identifier"]},
    # Two `?` and two `:` with spaces around them on one line: a ternary in a ternary. `x?.y` and `[k: v]` have none.
    "nested_ternary": {"regex": r"\s\?\s[^\n]*?\s\?\s[^\n]*?\s:\s[^\n]*?\s:\s",
                       "excluded_match_kinds": ["comment", "string"]},
    # A `var` at the start of a line is file-level state; a script's main.swift is made of it.
    "globals": {"regex": r"^(public |internal |fileprivate |private )?var\s", "excluded": r".*main\.swift"},
    # An unlabeled Bool (`_ flag: Bool`) is called as `f(true)`: the boolean trap. A labeled one reads fine there.
    "bool_params": {"regex": r"func\s+\w+[^\n]*[(,]\s*_\s+\w+\s*:\s*Bool\b",
                    "excluded_match_kinds": ["comment", "string"]},
}


def yaml_value(value: object) -> str:
    return f"[{', '.join(value)}]" if isinstance(value, list) else f"'{value}'"


def swiftlint_config(lim: Limits) -> str:
    rows = [f"only_rules: [{', '.join([*SWIFTLINT_METRICS, 'custom_rules'])}]"]
    rows += [f"{rule}: {{warning: {lim[metric][0]}, error: {UNREACHABLE}}}" for rule, metric in SWIFTLINT_SIZES.items()]
    rows.append("custom_rules:")
    for name, rule in SWIFT_CUSTOM_RULES.items():
        rows += [f"  {name}:", *(f"    {key}: {yaml_value(value)}" for key, value in rule.items()),
                 f"    message: {name}", "    severity: warning"]
    return "\n".join(rows) + "\n"


def measure_swift(r: Reader, rels: List[str], lim: Limits, _start: Path) -> None:
    exe = shutil.which("swiftlint")
    if not exe:
        r.notes.append("missing:swiftlint (brew install swiftlint)")
        return
    cfg = r.root.parent / f"{r.root.name}-swiftlint.yml"
    cfg.write_text(swiftlint_config(lim))
    rc, out, _ = run([exe, "lint", "--quiet", "--config", str(cfg), "--reporter", "json", *rels], r.root,
                     timeout=TOOL_TIMEOUT)
    for d in r.json(rc, out, []):
        rule = d.get("rule_id", "")
        metric = SWIFTLINT_METRICS.get(rule) or (rule if rule in SWIFT_CUSTOM_RULES else None)
        if metric:
            counted = metric in SMELL_PRESENCE or metric in SWIFT_CUSTOM_RULES
            value = 1 if counted else number(r"(\d+)\D*$", d.get("reason", ""))
            r.add(d.get("file", ""), int(d.get("line") or 0), metric, value)


MEASURES: List[Tuple[set, Callable[[Reader, List[str], Limits, Path], None]]] = [
    (PY_EXTS, measure_python), (JS_EXTS, measure_js), (GO_EXTS, measure_go), (SWIFT_EXTS, measure_swift),
]
# Rust and CSS have no smell tool here, but a file's length needs none, and jscpd reads them for duplicates.
LINES_ONLY_EXTS = RS_EXTS | CSS_EXTS
SMELL_EXTS = PY_EXTS | JS_EXTS | GO_EXTS | SWIFT_EXTS | LINES_ONLY_EXTS


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

