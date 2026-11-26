"""Measuring code smells with each language's tool, in a scratch tree, against broom's limits.

Each tool runs alone with a config broom writes, so the project's own configs never apply, and reports what
is past the soft limit as Raw rows: file, line, metric, the function's name (else the line's text), number.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .codelines import code_lines
from .config import NOTED, SMELL_PRESENCE
from .gitutil import run
from .gomeasure import go_text
from .jsmeasure import measure_js
from .reading import TOOL_TIMEOUT, Limits, Raw, Reader, match, number, quoted_name
from .rustmeasure import rust_text
from .swiftmeasure import swift_text
from .syntax import inside
from .toolchain import CSS_EXTS, GO_EXTS, JS_EXTS, PY_EXTS, RS_EXTS, SWIFT_EXTS

UNREACHABLE = 1_000_000  # a SwiftLint error level nothing reaches: broom tells hints from blocks itself
GO_MOD = "module broomsmells\n\ngo 1.22\n"


# ---------------------------------------------------------------- measures per language


def measure_files(r: Reader, rels: List[str], lim: Limits) -> None:
    """Record one row for each file in `rels` over its file-length limit: a file's length is its code lines."""
    for rel in rels:
        count = len(r.code.get(rel, ()))
        r.add(rel, 1, "file_lines", count if count > lim["file_lines"][0] else None, "file")


def nested_ternaries(r: Reader, rel: str, tree: ast.AST) -> None:
    """A conditional expression inside another one's test, value or alternative; ruff has no rule for it."""
    for node in ast.walk(tree):
        if isinstance(node, ast.IfExp):
            for part in (node.test, node.body, node.orelse):
                if isinstance(part, ast.IfExp):
                    r.add(rel, part.lineno, "nested_ternary", 1)


def python_sizes(r: Reader, rel: str, lim: Limits) -> None:
    """Function and class lengths from Python's own parser, which ruff doesn't measure in lines, each the code lines
    from its `def` or `class` line through its last; and its nested conditional expressions."""
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
            span = (child.lineno, child.end_lineno or child.lineno)
            r.add_length(rel, span, metric, lim[metric][0], prefix + child.name)
            walk(child, f"{prefix}{child.name}.")

    walk(tree, "")
    nested_ternaries(r, rel, tree)


RUFF_METRICS = {
    "C901": "complexity", "PLR0913": "params", "PLR1702": "nesting",
    "PGH003": "suppression", "PGH004": "suppression", "S110": "swallowed_error", "ERA001": "commented_code",
    "PLR2004": "magic_numbers", "T201": "debug_output", "T203": "debug_output", "ANN401": "type_escape",
    "PLW0603": "globals", "FBT001": "bool_params", "PT011": "broad_test_asserts",
    "BLE001": "broad_catch", "E722": "broad_catch",
    **{f"D10{n}": "missing_docs" for n in range(4)},  # module, class, method, function: public names only
    **{f"ARG00{n}": "unused_params" for n in range(1, 6)}, **{f"FIX00{n}": "todo" for n in range(1, 5)},
    # What the standard library and the common libraries have deprecated, by name: unittest aliases, `typing` aliases,
    # `mock`, `logging.warn`, numpy's, pandas' and pytest's; not typing's aliases, see typing_alias. ruff can't see a
    # project's own @deprecated.
    **{code: "deprecated_api" for code in ("UP005", "UP019", "UP021", "UP023", "UP026", "UP035", "G010", "PT020",
                                          "NPY001", "NPY003", "NPY201", "PD007")},
}


TYPING_MODULES = {"typing", "typing_extensions"}


def typing_lines(path: Path) -> Set[int]:
    """The lines of the `from typing import` statements (or typing_extensions') of the Python file at `path`, read
    from its tree; none when it doesn't parse."""
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return set()
    return {n for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module in TYPING_MODULES
            for n in range(node.lineno, (node.end_lineno or node.lineno) + 1)}


def typing_alias(r: Reader, d: dict) -> bool:
    """Whether a ruff finding is UP035 on a `from typing import` statement: the aliases deprecated since Python 3.9
    (List, Dict, Callable, ...). No version has dropped them, and every codebase older than that holds them, so
    counting them would bury the calls that are going."""
    if d.get("code") != "UP035":
        return False
    row = int((d.get("location") or {}).get("row") or 0)
    return row in typing_lines(r.root / r.rel(d.get("filename", "")))


def ruff_name(metric: str, msg: str) -> Optional[str]:
    """What names a ruff finding across versions: the function of a complexity, what a deprecation says; else None,
    and the line's text does."""
    if metric == "complexity":
        return quoted_name(msg)
    return msg if metric in NOTED else None


def measure_python(r: Reader, rels: List[str], lim: Limits, _start: Path) -> None:
    """Measure the Python files with ruff, for its complexity, argument and nesting findings; no ruff gives a note."""
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
        if metric and not typing_alias(r, d):
            name = ruff_name(metric, msg)
            value = 1 if metric in SMELL_PRESENCE else number(r"\((\d+) > \d+\)", msg)
            r.add(d.get("filename", ""), int(d["location"]["row"]), metric, value, name)


def nestif_complexity(depth: int) -> int:
    """nestif scores ifs nested inside an if 1, 2, 3, ... by depth, so `depth` levels score this much."""
    return depth * (depth - 1) // 2


def nesting_depth(complexity: int) -> int:
    """The nesting depth a nestif complexity of `complexity` stands for: the inverse of nestif_complexity."""
    return round((1 + (1 + 8 * complexity) ** 0.5) / 2)


def golangci_config(lim: Limits) -> str:
    """Linters that read syntax alone: the scratch tree holds only the changed files, so imports don't resolve,
    and one linter that needs types (goconst, staticcheck, unused) would stop them all. A type assertion that
    checks with a second result, `_` among them, can't panic, so it is no type escape (decision 042)."""
    revive = [f"{{name: argument-limit, arguments: [{lim['params'][0]}]}}", "{name: unused-parameter}",
              "{name: empty-block}", "{name: flag-parameter}", "{name: exported}",
              "{name: unchecked-type-assertion, arguments: [{acceptIgnoredAssertionResult: true}]}"]
    return "\n".join([
        'version: "2"',
        "linters:",
        "  default: none",
        "  enable: [nestif, gocognit, revive, mnd, nolintlint, godox]",
        "  settings:",
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
    ("gocognit", "", "complexity", r"cognitive complexity (\d+)", r"func `([^`]+)`"),
    ("nestif", "", "nesting", r"\(complexity: (\d+)\)", None),
    ("revive", "argument-limit", "params", r"but got (\d+)", None),
    ("revive", "unused-parameter", "unused_params", None, None),
    ("revive", "empty-block", "swallowed_error", None, None),
    ("revive", "flag-parameter", "bool_params", None, None),
    ("revive", "exported: exported ", "missing_docs", None, None),  # not "comment on exported ... form" or stutter
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


def measure_go(r: Reader, rels: List[str], lim: Limits, _start: Path) -> None:
    """Measure the Go files: what broom reads from their trees (the lengths among it), then the rest with
    golangci-lint in a scratch module; without golangci-lint, a note and no more rows. A setter's boolean
    parameter is no flag (decision 042)."""
    setters = go_text(r, rels, lim)
    exe = shutil.which("golangci-lint")
    if not exe:
        r.notes.append("missing:golangci-lint (brew install golangci-lint)")
        return
    (r.root / "go.mod").write_text(GO_MOD)
    cfg = r.root.parent / f"{r.root.name}-golangci.yml"
    cfg.write_text(golangci_config(lim))
    env = {"GOLANGCI_LINT_CACHE": str(r.root.parent / f"{r.root.name}-gocache")}
    rc, out, _ = run([exe, "run", "--allow-parallel-runners", "-c", str(cfg), "--output.json.path", "stdout",
                      "--output.text.path", "stderr", "--show-stats=false", "./..."], r.root, timeout=TOOL_TIMEOUT,
                     env=env)
    for d in (r.json(rc, out, {}) or {}).get("Issues") or []:
        read = golangci_read(d.get("FromLinter", ""), d.get("Text", ""))
        pos = d.get("Pos") or {}
        rel, line = r.rel(pos.get("Filename", "")), int(pos.get("Line", 0))
        if read and not (read[0] == "bool_params" and inside(line, setters.get(rel, []))):
            r.add(rel, line, *read)


SWIFTLINT_SIZES = {"function_body_length": "function_lines", "function_parameter_count": "params",
                   "cyclomatic_complexity": "complexity", "type_body_length": "type_lines"}
SWIFTLINT_METRICS = {
    **SWIFTLINT_SIZES, "blanket_disable_command": "suppression", "no_empty_block": "swallowed_error",
    "unused_parameter": "unused_params", "no_magic_numbers": "magic_numbers", "todo": "todo",
    "force_cast": "type_escape", "force_unwrapping": "type_escape", "force_try": "type_escape",
    "missing_docs": "missing_docs",
}


def swiftlint_config(lim: Limits) -> str:
    """The SwiftLint config text: the size rules at the limits in `lim`. What SwiftLint has no rule for is read from
    the syntax tree (swiftmeasure)."""
    rows = [f"only_rules: [{', '.join(SWIFTLINT_METRICS)}]"]
    rows += [f"{rule}: {{warning: {lim[metric][0]}, error: {UNREACHABLE}}}" for rule, metric in SWIFTLINT_SIZES.items()]
    return "\n".join(rows) + "\n"


def measure_swift(r: Reader, rels: List[str], lim: Limits, _start: Path) -> None:
    """Measure the Swift files: the smells read from the syntax tree, then the rest with swiftlint, under a config
    with the size rules; no swiftlint, a note."""
    swift_text(r, rels, lim)
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
        metric = SWIFTLINT_METRICS.get(rule)
        if metric:
            value = 1 if metric in SMELL_PRESENCE else number(r"(\d+)\D*$", d.get("reason", ""))
            r.add(d.get("file", ""), int(d.get("line") or 0), metric, value)


def measure_rust(r: Reader, rels: List[str], lim: Limits, _start: Path) -> None:
    """Measure the Rust files from their syntax trees: clippy, which needs the crate, runs in the real tree
    (realtree.py)."""
    rust_text(r, rels, lim)


MEASURES: List[Tuple[set, Callable[[Reader, List[str], Limits, Path], None]]] = [
    (PY_EXTS, measure_python), (JS_EXTS, measure_js), (GO_EXTS, measure_go), (SWIFT_EXTS, measure_swift),
    (RS_EXTS, measure_rust),
]
# CSS has no smell tool here, but a file's length needs only its comments read, and jscpd reads it for duplicates.
LINES_ONLY_EXTS = CSS_EXTS
SMELL_EXTS = PY_EXTS | JS_EXTS | GO_EXTS | SWIFT_EXTS | RS_EXTS | LINES_ONLY_EXTS


def measure(root: Path, contents: Dict[str, str], lim: Limits, start: Path, notes: List[str]) -> List[Raw]:
    """Write `contents` under the scratch tree `root`, measure it with every tool, and return the rows."""
    for rel, text in contents.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    reader = Reader(root, "broom", notes)
    reader.code = {rel: sorted(lines) for rel, lines in code_lines(contents, notes, root).items()}
    measure_files(reader, list(contents), lim)
    for exts, fn in MEASURES:
        rels = [rel for rel in contents if Path(rel).suffix in exts]
        if rels:
            reader.tool = fn.__name__.replace("measure_", "")
            fn(reader, rels, lim, start)
    return reader.rows

