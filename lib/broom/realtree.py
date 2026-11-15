"""Smells found by tools that need the project's own checkout: a typed linter or a module graph can't work on the
scratch copy of the changed files, whose imports don't resolve. These run in the real tree, and say where the
smells are; smells.py keeps those on the lines the change added, so no copy of the base is needed."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .config import DEAD_CODE
from .findings import failure
from .gitutil import run
from .jsmeasure import OXLINT_CATEGORIES
from .langlint import golangci_cache
from .pycycles import import_cycles
from .toolchain import GO_EXTS, JS_EXTS, RS_EXTS, find_up, resolve_bin

TOOL_TIMEOUT = 150
OUT_OF_TIME = "the time budget of this scan ran out before {tool} measured smells"


class Budget:
    """How long the tools of one pass may take between them. A scan of the whole repo, as at session start, has to
    end; the check of a commit has no budget, and each tool keeps its own timeout."""

    def __init__(self, seconds: Optional[float] = None) -> None:
        self.end = None if seconds is None else time.monotonic() + seconds

    def timeout(self) -> float:
        """What the next tool may take: its usual timeout, or what is left of the budget; 0 when none is."""
        if self.end is None:
            return TOOL_TIMEOUT
        return max(0.0, min(TOOL_TIMEOUT, self.end - time.monotonic()))


@dataclass
class Found:
    rel: str  # relative to the repo
    line: int
    metric: str
    tool: str
    key: str = ""  # what a dead-code finding names; a sized smell's function
    value: int = 1  # a sized smell's size


# The linters that need types, by what they find. They run with broom's own config, never the project's.
GO_TYPED = {"forbidigo": "debug_output", "gochecknoglobals": "globals", "gocritic": "commented_code",
            "unused": DEAD_CODE}
GO_CONFIG = """version: "2"
linters:
  default: none
  enable: [forbidigo, gochecknoglobals, gocritic, unused]
  settings:
    forbidigo:
      forbid:
        - pattern: '^(fmt\\.Print(f|ln)?|print|println)$'
    gocritic:
      disable-all: true
      enabled-checks: [commentedOutCode]
run: {tests: true, relative-path-mode: wd}
issues: {max-issues-per-linter: 0, max-same-issues: 0, uniq-by-line: false}
"""


def rel_of(repo: Path, path: Path) -> Optional[str]:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return None


def go_modules(repo: Path, rels: List[str]) -> Dict[Path, List[Path]]:
    """The Go files among `rels`, by the module each belongs to."""
    modules: Dict[Path, List[Path]] = {}
    for rel in rels:
        f = repo / rel
        mod = find_up(f.parent, ["go.mod"], repo) if f.suffix in GO_EXTS else None
        if mod:
            modules.setdefault(mod.parent, []).append(f)
    return modules


def go_found(repo: Path, rels: List[str], notes: List[str], budget: Budget) -> List[Found]:
    exe = shutil.which("golangci-lint")  # the lint check says when it is missing
    modules = go_modules(repo, rels)
    if not exe or not modules:
        return []
    found: List[Found] = []
    with tempfile.TemporaryDirectory(prefix="broom-realtree-") as tmp:
        cfg = Path(tmp) / "golangci.yml"
        cfg.write_text(GO_CONFIG)
        for module, files in modules.items():
            timeout = budget.timeout()
            if not timeout:
                notes.append(OUT_OF_TIME.format(tool="golangci-lint"))
                break
            pkgs = sorted({"./" + os.path.relpath(f.parent, module) for f in files})
            rc, out, err = run([exe, "run", "-c", str(cfg), "--output.json.path", "stdout",
                                "--output.text.path", "stderr", "--show-stats=false", *pkgs], module,
                               timeout=timeout, env={"GOLANGCI_LINT_CACHE": str(golangci_cache(module))})
            if rc is None:
                notes.append(f"timeout:golangci-lint measuring smells in {module}")
                continue
            try:
                issues = (json.loads(out) if out.strip() else {}).get("Issues") or []
            except ValueError:
                notes.append(f"golangci-lint failed measuring smells in {module}: {failure(out, err)}")
                continue
            found += go_issues(repo, module, issues)
    return found


def go_issues(repo: Path, module: Path, issues: List[dict]) -> List[Found]:
    found = []
    for i in issues:
        metric = GO_TYPED.get(i.get("FromLinter", ""))  # `typecheck`, a module that doesn't compile, has none
        rel = rel_of(repo, module / (i.get("Pos") or {}).get("Filename", ""))
        if metric and rel:
            what = re.sub(r" is unused.*$", "", i.get("Text", "")) if metric == DEAD_CODE else ""
            found.append(Found(rel, int((i.get("Pos") or {}).get("Line", 0)), metric, "golangci-lint", what))
    return found


def js_found(repo: Path, rels: List[str], notes: List[str], budget: Budget) -> List[Found]:
    """Import cycles through the changed TS/JS files: oxlint's `import/no-cycle` follows imports on disk, so the
    modules the changed files import have to be there. It finds each file's tsconfig itself."""
    files = [str(repo / rel) for rel in rels if Path(rel).suffix in JS_EXTS]
    exe = resolve_bin("oxlint", repo, repo)  # jsmeasure says when it is missing
    if not files or not exe:
        return []
    timeout = budget.timeout()
    if not timeout:
        notes.append(OUT_OF_TIME.format(tool="oxlint"))
        return []
    config = {"plugins": ["import"], "categories": {c: "off" for c in OXLINT_CATEGORIES},
              "rules": {"import/no-cycle": "warn"}}
    with tempfile.TemporaryDirectory(prefix="broom-realtree-") as tmp:
        cfg = Path(tmp) / "oxlint.json"
        cfg.write_text(json.dumps(config))
        rc, out, _ = run([exe, "-c", str(cfg), "-f", "json", "--no-error-on-unmatched-pattern", *files], repo,
                         timeout=timeout)
    if rc is None:
        notes.append("timeout:oxlint measuring import cycles")
        return []
    try:
        diagnostics = (json.loads(out) if out.strip() else {}).get("diagnostics") or []
    except ValueError:
        notes.append(f"oxlint failed measuring import cycles: {out.strip()[:120]}")
        return []
    found = []
    for d in diagnostics:
        rel = rel_of(repo, repo / d.get("filename", ""))
        if rel and "no-cycle" in d.get("code", ""):
            line = int(((d.get("labels") or [{}])[0].get("span") or {}).get("line", 0))
            found.append(Found(rel, line, "import_cycle", "oxlint"))
    return found


# clippy's lints, by what they find. The thresholds come from a clippy.toml in a directory of broom's own, so the
# project's is never read and nothing is written into the crate. A test may unwrap and print.
RUST_LINTS = {
    "clippy::too_many_arguments": "params", "clippy::fn_params_excessive_bools": "bool_params",
    "clippy::dbg_macro": "debug_output", "clippy::print_stdout": "debug_output",
    "clippy::print_stderr": "debug_output", "clippy::unwrap_used": "type_escape",
    "clippy::allow_attributes_without_reason": "suppression",
}
RUST_CONFIG = """too-many-arguments-threshold = {params}
max-fn-params-bools = 0
allow-unwrap-in-tests = true
allow-print-in-tests = true
allow-dbg-in-tests = true
"""
RUST_FLAGS = [flag for lint in RUST_LINTS for flag in ("-W", lint)]
FN_NAME = re.compile(r"\bfn\s+(\w+)")
ARGUMENTS = re.compile(r"\((\d+)/\d+\)")


def locate(repo: Path, crate: Path, name: str) -> Optional[str]:
    """The repo-relative path of a file clippy names: relative to the crate's workspace, so to it or a parent."""
    for base in (crate, *crate.parents):
        if (base / name).is_file():
            return rel_of(repo, base / name)
        if base == repo:
            break
    return None


def rust_messages(repo: Path, crate: Path, out: str) -> List[Found]:
    found = []
    for row in out.splitlines():
        try:
            d = json.loads(row)
        except ValueError:
            continue
        message = d.get("message") or {}
        metric = RUST_LINTS.get((message.get("code") or {}).get("code") or "")
        span = next((s for s in message.get("spans") or [] if s.get("is_primary")), None)
        rel = locate(repo, crate, span["file_name"]) if metric and span else None
        if not (rel and span):
            continue
        line = int(span["line_start"])
        text = (repo / rel).read_text(errors="replace").splitlines()[line - 1:line]
        name = FN_NAME.search(text[0]) if text else None
        size = ARGUMENTS.search(message.get("message", ""))
        found.append(Found(rel, line, metric, "clippy", name[1] if name else "function",
                           int(size[1]) if size else 1))
    return found


def rust_found(repo: Path, rels: List[str], params: int, notes: List[str], budget: Budget) -> List[Found]:
    """clippy's structural and presence lints in the crates the changed Rust files belong to. A crate is checked
    whole; smells.py keeps what is on the lines the change added."""
    cargo = shutil.which("cargo")
    manifests = [find_up((repo / rel).parent, ["Cargo.toml"], repo) for rel in rels if Path(rel).suffix in RS_EXTS]
    crates = sorted({m.parent for m in manifests if m})
    if not cargo or not crates:
        return []
    found: List[Found] = []
    with tempfile.TemporaryDirectory(prefix="broom-realtree-") as tmp:
        (Path(tmp) / "clippy.toml").write_text(RUST_CONFIG.format(params=params))
        for crate in crates:
            timeout = budget.timeout()
            if not timeout:
                notes.append(OUT_OF_TIME.format(tool="clippy"))
                break
            rc, out, _ = run([cargo, "clippy", "--message-format=json", "--quiet", "--", *RUST_FLAGS], crate,
                             timeout=timeout, env={"CLIPPY_CONF_DIR": tmp})
            if rc is None:
                notes.append(f"timeout:cargo clippy measuring smells in {crate} (cold build?)")
                continue
            found += rust_messages(repo, crate, out)
    return found


def find_in_real_tree(repo: Path, rels: List[str], params: int, notes: List[str],
                      budget: Optional[Budget] = None) -> List[Found]:
    """What the tools that need the real tree find in the files `rels` (their package or crate, more exactly).
    `params` is the soft limit on a function's parameters. The quick tools go first, so clippy, which may be
    building a crate cold, gets what is left of a `budget`."""
    budget = budget or Budget()
    found = go_found(repo, rels, notes, budget) + js_found(repo, rels, notes, budget)
    found += [Found(rel, line, "import_cycle", "broom") for rel, line in import_cycles(repo, rels)]
    return found + rust_found(repo, rels, params, notes, budget)
