"""Each language's files and tools: extensions, config file names, and which formatter and linters a project uses,
found by walking up from a file to the repo root."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .gitutil import git_root
from .state import read_jsonc

GO_EXTS = {".go"}
JS_EXTS = {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
RS_EXTS = {".rs"}
PY_EXTS = {".py", ".pyi"}
SWIFT_EXTS = {".swift"}
# Linted and served by a language server; formatted, like WEB_EXTS, by the project's JS-side formatter.
CSS_EXTS = {".css", ".scss", ".less"}
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
STYLELINT_CFG = (
    ".stylelintrc", ".stylelintrc.json", ".stylelintrc.yaml", ".stylelintrc.yml", ".stylelintrc.js",
    ".stylelintrc.cjs", ".stylelintrc.mjs", ".stylelintrc.ts", ".stylelintrc.cts", ".stylelintrc.mts",
    "stylelint.config.js", "stylelint.config.cjs", "stylelint.config.mjs", "stylelint.config.ts",
    "stylelint.config.cts", "stylelint.config.mts",
)
# The configs defaults/stylelintrc.yml extends per dialect: stylelint loads them from the project.
DIALECT_DEFAULTS = {".scss": ("SCSS", "stylelint-config-recommended-scss"),
                    ".less": ("Less", "stylelint-config-recommended-less")}
GOLANGCI_CFG = (".golangci.yml", ".golangci.yaml", ".golangci.toml", ".golangci.json")
RUFF_CFG = ("ruff.toml", ".ruff.toml")
PY_ROOT_MARKERS = ("pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg", "setup.py")
SWIFTLINT_CFG = ".swiftlint.yml"  # SwiftLint reads no other name, .swiftlint.yaml included
SWIFT_FORMAT_CFG = ".swift-format"  # swift-format, Apple's, in the toolchain since Swift 6
SWIFTFORMAT_CFG = ".swiftformat"  # SwiftFormat, Nick Lockwood's


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
    if ext in CSS_EXTS:
        return "css"
    if ext in SWIFT_EXTS:
        return "swift"
    return None


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


def in_node_modules(rel: str, start: Path, stop: Optional[Path]) -> Optional[Path]:
    """The nearest node_modules/<rel> in `start` or its parents, never above `stop`: where Node finds it."""
    d = start
    while True:
        cand = d / "node_modules" / rel
        if cand.exists():
            return cand
        if d == stop or d.parent == d:
            return None
        d = d.parent


def resolve_bin(name: str, start: Path, stop: Optional[Path], local_only: bool = False) -> Optional[str]:
    """Project-local node_modules/.bin first (never above `stop`), then PATH."""
    local = in_node_modules(f".bin/{name}", start, stop)
    if local:
        return str(local)
    return None if local_only else shutil.which(name)


def boundary(path: Path) -> Path:
    """Where upward config searches stop: the git root, else the file's directory."""
    return git_root(path.parent) or path.parent


def pkg_has_key(d: Path, key: str) -> bool:
    pkg = d / "package.json"
    return pkg.is_file() and key in read_jsonc(pkg)


def pkg_scripts_mention(d: Path, needle: str) -> bool:
    pkg = d / "package.json"
    scripts = read_jsonc(pkg).get("scripts") if pkg.is_file() else None
    return isinstance(scripts, dict) and any(needle in str(v) for v in scripts.values())


def pkg_depends(d: Path, name: str, stop: Path) -> bool:
    """Whether the nearest package.json at or above `d` lists `name` as a dependency."""
    pkg = find_up(d, ["package.json"], stop)
    data = read_jsonc(pkg) if pkg else {}
    return any(isinstance(data.get(k), dict) and name in data[k] for k in ("dependencies", "devDependencies"))


def _biome_enabled(d: Path, *sections: str) -> bool:
    """Whether `d` has a biome config that leaves every one of `sections` (dotted: `css.linter`) switched on."""
    for n in BIOME_CFG:
        if (d / n).is_file():
            cfg = read_jsonc(d / n)
            for section in sections:
                sec = cfg
                for key in section.split("."):
                    sec = sec.get(key) if isinstance(sec, dict) else None
                if isinstance(sec, dict) and sec.get("enabled") is False:
                    return False
            return True
    return False


def js_formatter(path: Path, stop: Path) -> Optional[Tuple[str, Path]]:
    """(tool, config dir) of the nearest configured JS-side formatter, or None."""
    d = path.parent
    while True:
        if _biome_enabled(d, "formatter"):
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
        if _biome_enabled(d, "linter"):
            found.append(("biome", d))
        if found:
            return found
        if d == stop or d.parent == d:
            break
        d = d.parent
    pkg = find_up(path.parent, ["package.json"], stop)
    return [("oxlint-default", pkg.parent if pkg else path.parent)]


def css_linters(path: Path, stop: Path) -> List[Tuple[str, Path]]:
    """Like js_linters: the project's stylelint, biome or ESLint with @eslint/css at the nearest level that has
    any, else `stylelint-default` run from the package (or the repo root: CSS has no project file of its own).
    biome and @eslint/css don't read SCSS or Less, so for those only stylelint counts."""
    plain = path.suffix.lower() == ".css"
    d = path.parent
    while True:
        found = []
        if any((d / n).exists() for n in STYLELINT_CFG) or pkg_has_key(d, "stylelint"):
            found.append(("stylelint", d))
        if plain and _biome_enabled(d, "linter", "css.linter"):
            found.append(("biome", d))
        if plain and any((d / n).exists() for n in ESLINT_CFG) and pkg_depends(d, "@eslint/css", stop):
            found.append(("eslint", d))
        if found:
            return found
        if d == stop or d.parent == d:
            break
        d = d.parent
    pkg = find_up(path.parent, ["package.json"], stop)
    return [("stylelint-default", pkg.parent if pkg else stop)]


def swift_formatter(path: Path, stop: Path) -> Optional[Tuple[str, Path]]:
    """(tool, config dir) of the nearest Swift formatter config, or None. Swift has two formatters and neither is
    everyone's, so, as for JS, there is none without a config."""
    d = path.parent
    while True:
        if (d / SWIFTFORMAT_CFG).is_file():
            return "swiftformat", d
        if (d / SWIFT_FORMAT_CFG).is_file():
            return "swift-format", d
        if d == stop or d.parent == d:
            return None
        d = d.parent


def swift_format_cmd() -> Optional[List[str]]:
    """swift-format: a standalone install (brew) first, else the toolchain's `swift format` (Swift 6 and later)."""
    exe = shutil.which("swift-format")
    if exe:
        return [exe]
    swift = shutil.which("swift")
    return [swift, "format"] if swift else None


def swift_linter(path: Path, stop: Path) -> Tuple[str, Path]:
    """("swiftlint", dir) when the project has a .swiftlint.yml, else ("swiftlint-default", package or repo root).
    The outermost config up to `stop`: SwiftLint run there, as a project runs it, also applies the nested ones."""
    outer = None
    d = path.parent
    while True:
        if (d / SWIFTLINT_CFG).is_file():
            outer = d
        if d == stop or d.parent == d:
            break
        d = d.parent
    if outer:
        return "swiftlint", outer
    pkg = find_up(path.parent, ["Package.swift"], stop)
    return "swiftlint-default", pkg.parent if pkg else stop


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
