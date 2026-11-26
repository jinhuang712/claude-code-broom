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
from typing import Dict, Iterator, List, Optional, Tuple

from .config import DEAD_CODE, OPTIONAL_NOTE
from .findings import failure
from .foldercycles import js_folder_cycles, python_folder_cycles
from .gomeasure import assigned_globals
from .gitutil import run
from .jsmeasure import OXLINT_CATEGORIES
from .langlint import golangci_cache
from .pycycles import import_cycles
from .rustcycles import rust_folder_cycles, rust_import_cycles
from .rustlint import RUST_LINTS, RUST_FLAGS, config_text, read as rust_read, thresholds
from .rustmeasure import FN_RULES, rust_tree
from .state import DATA_ROOT, prune_dirs, short_hash
from .swiftcheck import swift_deprecated
from .swiftmeasure import swift_unused
from .syntax import Match
from .toolchain import GO_EXTS, JS_EXTS, RS_EXTS, find_up, resolve_bin

TOOL_TIMEOUT = 150
OUT_OF_TIME = "timeout:the time of this scan ran out before {tool} measured smells"


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
    """A smell found in the real tree: where it is (`rel`, `line`), its metric and tool, and its key and value."""
    rel: str  # relative to the repo
    line: int
    metric: str
    tool: str
    key: str = ""  # what a dead-code finding names; a sized smell's function
    value: int = 1  # a sized smell's size


# The linters that need types, by what they find. They run with broom's own config, never the project's.
GO_TYPED = {"gocritic": "commented_code", "unused": DEAD_CODE,
            "staticcheck": "deprecated_api"}  # of staticcheck only SA1019, a deprecated call
GO_CONFIG = """version: "2"
linters:
  default: none
  enable: [gocritic, staticcheck, unused]
  settings:
    staticcheck:
      checks: ["-all", "SA1019"]
    gocritic:
      disable-all: true
      enabled-checks: [commentedOutCode]
run: {tests: true, relative-path-mode: wd}
issues: {max-issues-per-linter: 0, max-same-issues: 0, uniq-by-line: false}
"""


def rel_of(repo: Path, path: Path) -> Optional[str]:
    """`path` relative to `repo` as a POSIX path, or None when it lies outside the repo."""
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
    """Lint the Go modules of the files in `rels` with golangci-lint's typed linters; a spent budget adds a note."""
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
            rc, out, err = run([exe, "run", "--allow-parallel-runners", "-c", str(cfg), "--output.json.path", "stdout",
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
    """Turn golangci-lint's `issues` for `module` into Found rows: typed linters, files inside the repo only."""
    found = []
    for i in issues:
        linter, text = i.get("FromLinter", ""), i.get("Text", "")
        metric = GO_TYPED.get(linter)  # `typecheck`, a module that doesn't compile, has none
        rel = rel_of(repo, module / (i.get("Pos") or {}).get("Filename", ""))
        if metric and rel and (linter != "staticcheck" or text.startswith("SA1019")):
            found.append(Found(rel, int((i.get("Pos") or {}).get("Line", 0)), metric, "golangci-lint",
                               go_key(metric, text)))
    return found


def go_state(repo: Path, rels: List[str], notes: List[str], budget: Budget) -> List[Found]:
    """A package variable that a function of the changed Go files assigns, read from the trees of their packages'
    files, which only the real tree holds (decision 042)."""
    if not any(Path(rel).suffix in GO_EXTS for rel in rels):
        return []
    timeout = budget.timeout()
    if not timeout:
        notes.append(OUT_OF_TIME.format(tool="ast-grep"))
        return []
    return [Found(rel, line, "globals", "broom") for rel, line in assigned_globals(repo, rels, notes, timeout)]


def go_key(metric: str, text: str) -> str:
    """What a golangci-lint finding names: the item dead code is about, or a deprecation as `item is deprecated:
    note`, the note being what says what replaced it (staticcheck words it `item has been deprecated since Go 1.18
    [and an alternative ...]: note`); nothing for the rest."""
    if metric == DEAD_CODE:
        return re.sub(r" is unused.*$", "", text)
    if metric != "deprecated_api":
        return ""
    m = re.match(r"SA1019: (\S+) has been deprecated[^:]*: (.*)$", text.strip(), re.S)
    return f"{m[1]} is deprecated: {m[2]}" if m else text.removeprefix("SA1019: ").strip()


NO_TSGOLINT = (f"{OPTIONAL_NOTE}oxlint-tsgolint is missing, so deprecated TS/JS APIs aren't measured "
               "(npm i -g oxlint-tsgolint)")


def js_config(*, typed: bool) -> dict:
    """The oxlint config for the real tree: import cycles, and where tsgolint gives it types, deprecated calls."""
    rules = {"import/no-cycle": "warn", **({"typescript/no-deprecated": "warn"} if typed else {})}
    return {"plugins": ["import", "typescript"] if typed else ["import"],
            "categories": {c: "off" for c in OXLINT_CATEGORIES}, "rules": rules}


def js_row(repo: Path, d: dict) -> Optional[Found]:
    """The smell one oxlint diagnostic of the real-tree run holds: a cycle or a deprecated call; None for the rest."""
    rel, code = rel_of(repo, repo / d.get("filename", "")), d.get("code", "")
    line = int(((d.get("labels") or [{}])[0].get("span") or {}).get("line", 0))
    if rel and "no-cycle" in code:
        return Found(rel, line, "import_cycle", "oxlint")
    if rel and "no-deprecated" in code:
        return Found(rel, line, "deprecated_api", "oxlint", d.get("message", ""))
    return None


def js_found(repo: Path, rels: List[str], notes: List[str], budget: Budget) -> List[Found]:
    """Import cycles and deprecated calls in the changed TS/JS files, from one oxlint run. `import/no-cycle` follows
    imports on disk, so the modules the changed files import have to be there; it finds each file's tsconfig itself.
    `typescript/no-deprecated` needs types, so it runs with `--type-aware` where tsgolint is installed (it makes the
    run slower, and a timeout loses the cycles too); without it an `optional:` note says what isn't measured."""
    files = [str(repo / rel) for rel in rels if Path(rel).suffix in JS_EXTS]
    exe = resolve_bin("oxlint", repo, repo)  # jsmeasure says when it is missing
    if not files or not exe:
        return []
    timeout = budget.timeout()
    if not timeout:
        notes.append(OUT_OF_TIME.format(tool="oxlint"))
        return []
    typed = bool(resolve_bin("tsgolint", repo, repo))
    if not typed:
        notes.append(NO_TSGOLINT)  # a hook keeps it to itself: the doctor lists the tool as optional
    with tempfile.TemporaryDirectory(prefix="broom-realtree-") as tmp:
        cfg = Path(tmp) / "oxlint.json"
        cfg.write_text(json.dumps(js_config(typed=typed)))
        rc, out, _ = run([exe, "-c", str(cfg), "-f", "json", "--no-error-on-unmatched-pattern",
                          *(["--type-aware"] if typed else []), *files], repo, timeout=timeout)
    if rc is None:
        notes.append("timeout:oxlint measuring import cycles and deprecated calls")
        return []
    try:
        diagnostics = (json.loads(out) if out.strip() else {}).get("diagnostics") or []
    except ValueError:
        notes.append(f"oxlint failed measuring import cycles and deprecated calls: {out.strip()[:120]}")
        return []
    return [row for row in (js_row(repo, d) for d in diagnostics) if row]


def locate(repo: Path, crate: Path, name: str) -> Optional[str]:
    """The repo-relative path of a file clippy names: relative to the crate's workspace, so to it or a parent."""
    for base in (crate, *crate.parents):
        if (base / name).is_file():
            return rel_of(repo, base / name)
        if base == repo:
            break
    return None


def diagnostics(out: str) -> Iterator[dict]:
    """The compiler messages among the JSON rows cargo prints."""
    for row in out.splitlines():
        try:
            message = json.loads(row).get("message")
        except (ValueError, AttributeError):
            continue
        if isinstance(message, dict):
            yield message


def message_found(repo: Path, crate: Path, message: dict, soft: Dict[str, int],
                  trees: Dict[str, List[Match]]) -> Iterator[Found]:
    """The smells one compiler message holds. `trees` keeps the syntax-tree matches of the files it has read."""
    metric = RUST_LINTS.get((message.get("code") or {}).get("code") or "")
    if not metric:
        return
    spans = [s for s in message.get("spans") or [] if s.get("is_primary")]
    for span in spans if metric == DEAD_CODE else spans[:1]:  # dead code names several items
        rel = locate(repo, crate, span["file_name"])
        if rel is None:
            continue
        read = rust_read(metric, message, span, trees.get(rel, []), soft)
        if read:
            yield Found(rel, int(span["line_start"]), metric, "clippy", *read)


def rust_messages(repo: Path, crate: Path, out: str, soft: Dict[str, int]) -> List[Found]:
    """What clippy and rustc found, as the smells RUST_LINTS names. `soft` holds the soft limits clippy ran with."""
    found: Dict[Tuple[str, int, str, str], Found] = {}
    messages = list(diagnostics(out))
    named = {rel for m in messages for s in m.get("spans") or [] if s.get("is_primary")
             for rel in [locate(repo, crate, s["file_name"])] if rel is not None}
    trees = rust_tree(repo, sorted(named), [], FN_RULES)  # one run of ast-grep for every file the messages name
    for message in messages:
        for row in message_found(repo, crate, message, soft, trees):
            found.setdefault((row.rel, row.line, row.metric, row.key), row)  # a crate built twice says things twice
    return list(found.values())


CLIPPY_DIRS = DATA_ROOT / "clippy"


def clippy_dirs(crate: Path, soft: Dict[str, int]) -> Tuple[Path, Path]:
    """Where broom's clippy run keeps its config and its build output, the same each time. cargo counts a different
    CLIPPY_CONF_DIR (a fresh temporary directory per run was one) and different clippy arguments as a reason to check
    the crate again, so the project's own clippy run and this one would each throw away the other's work. With a
    stable config path and a target directory of its own, both stay fresh. Unused for 7 days, they go."""
    conf = CLIPPY_DIRS / "conf" / "-".join(str(n) for n in thresholds(soft).values())
    conf.mkdir(parents=True, exist_ok=True)
    text = config_text(soft)
    if not (conf / "clippy.toml").exists() or (conf / "clippy.toml").read_text() != text:
        (conf / "clippy.toml").write_text(text)
    target = CLIPPY_DIRS / "target" / short_hash(str(crate))
    target.mkdir(parents=True, exist_ok=True)
    os.utime(target)
    prune_dirs(CLIPPY_DIRS / "target", 7)
    return conf, target


def rust_found(repo: Path, rels: List[str], soft: Dict[str, int], notes: List[str], budget: Budget) -> List[Found]:
    """clippy's structural and presence lints and rustc's dead-code and unused-parameter warnings in the crates the
    changed Rust files belong to, from one clippy run per crate. A crate is checked whole; smells.py keeps what is
    on the lines the change added. Tests are never built, so the new lints leave them out as the old ones did."""
    cargo = shutil.which("cargo")
    manifests = [find_up((repo / rel).parent, ["Cargo.toml"], repo) for rel in rels if Path(rel).suffix in RS_EXTS]
    crates = sorted({m.parent for m in manifests if m})
    if not cargo or not crates:
        return []
    found: List[Found] = []
    for crate in crates:
        timeout = budget.timeout()
        if not timeout:
            notes.append(OUT_OF_TIME.format(tool="clippy"))
            break
        conf, target = clippy_dirs(crate, soft)
        rc, out, _ = run([cargo, "clippy", "--message-format=json", "--quiet", "--", *RUST_FLAGS], crate,
                         timeout=timeout, env={"CLIPPY_CONF_DIR": str(conf), "CARGO_TARGET_DIR": str(target)})
        if rc is None:
            notes.append(f"timeout:cargo clippy measuring smells in {crate} (cold build?)")
            continue
        found += rust_messages(repo, crate, out, soft)
    return found


def find_in_real_tree(repo: Path, rels: List[str], soft: Dict[str, int], notes: List[str],
                      budget: Optional[Budget] = None) -> List[Found]:
    """What the tools that need the real tree find in the files `rels` (their package or crate, more exactly).
    `soft` maps a sized smell to its soft limit; clippy gets those of rustlint.SOFT_LIMITS. The quick tools go
    first, so clippy, which may be building a crate cold, gets what is left of a `budget`."""
    budget = budget or Budget()
    found = go_found(repo, rels, notes, budget) + go_state(repo, rels, notes, budget)
    found += js_found(repo, rels, notes, budget)
    for metric, cycles in (("import_cycle", import_cycles), ("import_cycle", rust_import_cycles),
                           ("folder_cycle", python_folder_cycles), ("folder_cycle", rust_folder_cycles)):
        found += [Found(rel, line, metric, "broom") for rel, line in cycles(repo, rels)]
    found += [Found(rel, line, "folder_cycle", "dependency-cruiser")
              for rel, line in js_folder_cycles(repo, rels, notes, budget.timeout)]
    found += [Found(rel, line, DEAD_CODE, "broom", what) for rel, line, what in swift_unused(repo, rels)]
    found += [Found(rel, line, "deprecated_api", "swiftc", what)
              for rel, line, what in swift_deprecated(repo, rels, notes, budget.timeout)]
    return found + rust_found(repo, rels, soft, notes, budget)
