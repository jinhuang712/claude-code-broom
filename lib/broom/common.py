"""Shared helpers: settings, project detection, tool lookup, git, per-session state."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Resolved from this file, not CLAUDE_PLUGIN_ROOT: that variable is set for hooks but not for `broom` run from Bash.
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
# Hooks get CLAUDE_PLUGIN_DATA; the fallback is the same directory Claude Code assigns broom@claude-code-broom,
# so `broom` run from Bash shares state (the known-issue list) with the hooks.
DATA_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".claude" / "plugins" / "data" / "broom-claude-code-broom")
DEFAULTS = PLUGIN_ROOT / "defaults"

SETTINGS = {
    "format_on": ("commit", ("commit", "edit", "off")),
    "check_on": ("commit", ("commit", "stop", "off")),
    "format_scope": ("changed", ("changed", "file")),
}
PLUGIN_ID = "broom@claude-code-broom"


def setting(name: str) -> str:
    """A userConfig value. Claude Code exports those to hooks as CLAUDE_PLUGIN_OPTION_<NAME> but not to commands
    run through Bash, so `broom` there reads them where Claude Code stores them, in the user settings file."""
    default, allowed = SETTINGS[name]
    value = os.environ.get(f"CLAUDE_PLUGIN_OPTION_{name.upper()}")
    if value is None:
        config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"
        try:
            options = json.loads(config.read_text()).get("pluginConfigs", {}).get(PLUGIN_ID, {}).get("options", {})
            value = str(options.get(name, ""))
        except (OSError, ValueError, AttributeError):
            value = ""
    value = value.strip().lower()
    return value if value in allowed else default

GO_EXTS = {".go"}
JS_EXTS = {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
RS_EXTS = {".rs"}
PY_EXTS = {".py", ".pyi"}
# Other file types a project's JS-side formatter (oxfmt, biome, prettier) handles.
WEB_EXTS = {
    ".json", ".jsonc", ".css", ".scss", ".less", ".md", ".mdx", ".yaml", ".yml",
    ".html", ".vue", ".svelte", ".astro", ".graphql",
}

BIOME_CFG = ("biome.json", "biome.jsonc")
OXFMT_CFG = (".oxfmtrc.json", ".oxfmtrc.jsonc", "oxfmt.config.ts", "oxfmt.config.js", "oxfmt.config.mjs")
PRETTIER_CFG = (
    ".prettierrc", ".prettierrc.json", ".prettierrc.json5", ".prettierrc.yaml", ".prettierrc.yml",
    ".prettierrc.toml", ".prettierrc.js", ".prettierrc.cjs", ".prettierrc.mjs", ".prettierrc.ts",
    "prettier.config.js", "prettier.config.cjs", "prettier.config.mjs", "prettier.config.ts",
)
OXLINT_CFG = (".oxlintrc.json", ".oxlintrc.jsonc", "oxlint.config.ts", "oxlint.config.js", "oxlint.config.mjs")
ESLINT_CFG = (
    "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
    "eslint.config.mts", "eslint.config.cts", ".eslintrc", ".eslintrc.js", ".eslintrc.cjs",
    ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
)
GOLANGCI_CFG = (".golangci.yml", ".golangci.yaml", ".golangci.toml", ".golangci.json")
RUFF_CFG = ("ruff.toml", ".ruff.toml")
PY_ROOT_MARKERS = ("pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg", "setup.py")


def lang_of(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    if ext in GO_EXTS:
        return "go"
    if ext in JS_EXTS:
        return "js"
    if ext in RS_EXTS:
        return "rust"
    if ext in PY_EXTS:
        return "py"
    return None


# ---------------------------------------------------------------- hook I/O


def read_hook_input() -> dict:
    try:
        data = json.load(sys.stdin)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


# ---------------------------------------------------------------- processes


def run(cmd: List[str], cwd: Path, timeout: float = 90) -> Tuple[Optional[int], str, str]:
    """Run a command; the return code is None when it timed out."""
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return None, "", ""
    except OSError as e:
        return -1, "", str(e)


def git(args: List[str], cwd: Path) -> Optional[str]:
    rc, out, _ = run(["git", *args], cwd, timeout=15)
    return out if rc == 0 else None


_git_roots: Dict[Path, Optional[Path]] = {}


def git_root(d: Path) -> Optional[Path]:
    if d not in _git_roots:
        out = git(["rev-parse", "--show-toplevel"], d) if d.is_dir() else None
        _git_roots[d] = Path(out.strip()).resolve() if out else None
    return _git_roots[d]


def git_changed_files(root: Path) -> List[Path]:
    """Tracked files changed against HEAD plus untracked, non-ignored files."""
    files: List[str] = []
    out = git(["diff", "--name-only", "--no-renames", "HEAD"], root)
    if out is None:  # no commits yet
        out = git(["diff", "--name-only", "--cached"], root) or ""
    files += out.splitlines()
    files += (git(["ls-files", "--others", "--exclude-standard"], root) or "").splitlines()
    return [p for p in ((root / f).resolve() for f in files if f) if p.is_file()]


# ---------------------------------------------------------------- lookup


def find_up(start: Path, names: Iterable[str], stop: Optional[Path]) -> Optional[Path]:
    """Nearest file named one of `names` in `start` or its parents, up to `stop` inclusive."""
    names = list(names)
    d = start
    while True:
        for n in names:
            p = d / n
            if p.exists():
                return p
        if d == stop or d.parent == d:
            return None
        d = d.parent


def resolve_bin(name: str, start: Path, stop: Optional[Path], local_only: bool = False) -> Optional[str]:
    """Project-local node_modules/.bin first (never above `stop`), then PATH."""
    d = start
    while True:
        cand = d / "node_modules" / ".bin" / name
        if cand.exists():
            return str(cand)
        if d == stop or d.parent == d:
            break
        d = d.parent
    return None if local_only else shutil.which(name)


def boundary(path: Path) -> Path:
    """Where upward config searches stop: the git root, else the file's directory."""
    return git_root(path.parent) or path.parent


def read_jsonc(path: Path) -> dict:
    try:
        text = path.read_text()
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r'^\s*//.*$|(?<=[,{\[\s])//[^"\n]*$', "", text, flags=re.M)
        text = re.sub(r",(\s*[}\]])", r"\1", text)
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def pkg_has_key(d: Path, key: str) -> bool:
    pkg = d / "package.json"
    return pkg.is_file() and key in read_jsonc(pkg)


def pkg_scripts_mention(d: Path, needle: str) -> bool:
    pkg = d / "package.json"
    scripts = read_jsonc(pkg).get("scripts") if pkg.is_file() else None
    return isinstance(scripts, dict) and any(needle in str(v) for v in scripts.values())


def _biome_section_enabled(d: Path, section: str) -> bool:
    for n in BIOME_CFG:
        if (d / n).is_file():
            sec = read_jsonc(d / n).get(section)
            return not (isinstance(sec, dict) and sec.get("enabled") is False)
    return False


def js_formatter(path: Path, stop: Path) -> Optional[Tuple[str, Path]]:
    """(tool, config dir) of the nearest configured JS-side formatter, or None."""
    d = path.parent
    while True:
        if _biome_section_enabled(d, "formatter"):
            return "biome", d
        if any((d / n).exists() for n in OXFMT_CFG):
            return "oxfmt", d
        if any((d / n).exists() for n in PRETTIER_CFG) or pkg_has_key(d, "prettier"):
            return "prettier", d
        if d == stop or d.parent == d:
            return None
        d = d.parent


def js_linters(path: Path, stop: Path) -> List[Tuple[str, Path]]:
    """Lint tools configured at the nearest level that has any; `oxlint-default` when none do."""
    d = path.parent
    while True:
        found = []
        if any((d / n).exists() for n in OXLINT_CFG):
            found.append(("oxlint", d))
        if any((d / n).exists() for n in ESLINT_CFG) or pkg_has_key(d, "eslintConfig"):
            found.append(("eslint", d))
        if _biome_section_enabled(d, "linter"):
            found.append(("biome", d))
        if found:
            return found
        if d == stop or d.parent == d:
            break
        d = d.parent
    pkg = find_up(path.parent, ["package.json"], stop)
    return [("oxlint-default", pkg.parent if pkg else path.parent)]


def ruff_configured(path: Path, stop: Path) -> bool:
    if find_up(path.parent, RUFF_CFG, stop):
        return True
    py = find_up(path.parent, ["pyproject.toml"], stop)
    try:
        return bool(py) and "[tool.ruff" in py.read_text()
    except OSError:
        return False


def rust_edition(path: Path, stop: Path) -> str:
    cargo = find_up(path.parent, ["Cargo.toml"], stop)
    while cargo:
        try:
            text = cargo.read_text()
        except OSError:
            break
        m = re.search(r'^\s*edition\s*=\s*"(\d{4})"', text, flags=re.M)
        if m:
            return m.group(1)
        if cargo.parent == stop or cargo.parent.parent == cargo.parent:
            break
        cargo = find_up(cargo.parent.parent, ["Cargo.toml"], stop)  # workspace-inherited edition
    return "2021"


# ---------------------------------------------------------------- session state


def session_dir(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    d = DATA_ROOT / "sessions" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def append_line(path: Path, text: str) -> None:
    with open(path, "a") as f:
        f.write(text + "\n")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def prune_sessions(max_age_days: float = 7) -> None:
    root = DATA_ROOT / "sessions"
    cutoff = time.time() - max_age_days * 86400
    for d in root.glob("*") if root.is_dir() else []:
        try:
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def short_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- changed lines


class ChangedLines:
    """Line numbers of each file that differ from `base` (the index against HEAD when `cached`); None means
    every line counts."""

    HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    def __init__(self, base: str = "HEAD", cached: bool = False) -> None:
        self.base = base
        self.cached = cached
        self._cache: Dict[Path, Optional[Set[int]]] = {}

    def get(self, f: Path) -> Optional[Set[int]]:
        if f not in self._cache:
            self._cache[f] = self._compute(f)
        return self._cache[f]

    def _compute(self, f: Path) -> Optional[Set[int]]:
        root = git_root(f.parent)
        if root is None or git(["rev-parse", "--verify", "-q", self.base], root) is None:
            return None
        if git(["ls-files", "--error-unmatch", str(f)], root) is None:
            return None  # untracked: all of it is new
        mode = ["--cached"] if self.cached else []
        out = git(["diff", "-U0", "--no-color", "--no-ext-diff", *mode, self.base, "--", str(f)], root) or ""
        lines: Set[int] = set()
        for row in out.splitlines():
            m = self.HUNK.match(row)
            if not m:
                continue
            start, count = int(m.group(1)), int(m.group(2) or 1)
            lines.update({start, start + 1} if count == 0 else range(start, start + count))
        return lines
