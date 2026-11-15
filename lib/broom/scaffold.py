"""`broom init`: the default configs a project doesn't have yet. Never overwrites."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Iterable, List

from .gitutil import run
from .state import DEFAULTS
from .toolchain import (
    BIOME_CFG, ESLINT_CFG, GOLANGCI_CFG, OXFMT_CFG, OXLINT_CFG, PRETTIER_CFG, SWIFT_FORMAT_CFG, SWIFTFORMAT_CFG,
    pkg_has_key, ruff_configured,
)

GOLANGCI_FORMATTERS = """
formatters:
  enable:
    - gofumpt
    - goimports
"""
RUFF_DEFAULT = """[lint]
select = ["E4", "E7", "E9", "F", "B", "UP"]
"""
# swift-format, since the toolchain ships it (Swift 6 and later): nothing to install. Its own defaults are 2 spaces
# and 100 columns; Xcode indents with 4, as most Swift code does, so a reformatted line keeps the file's indent, and
# 120 columns (SwiftLint's line_length) re-wraps fewer lines of code written without a limit. JSON allows no
# comments, so this note lives here.
SWIFT_FORMAT_DEFAULT = """{
  "version": 1,
  "indentation": { "spaces": 4 },
  "lineLength": 120
}
"""


class Scaffold:
    """What `broom init` adds to one project: a config a language lacks. With `dry_run` it only says what it would."""

    def __init__(self, root: Path, *, dry_run: bool) -> None:
        self.root = root
        self.dry_run = dry_run
        self.actions: List[str] = []

    def has(self, names: Iterable[str]) -> bool:
        return any((self.root / n).exists() for n in names)

    def write(self, name: str, text: str) -> None:
        self.actions.append(f"{'would add' if self.dry_run else 'added'} {name}")
        if not self.dry_run:
            (self.root / name).write_text(text)

    def go(self) -> None:
        if not self.has(GOLANGCI_CFG):
            self.write(".golangci.yml", (DEFAULTS / "golangci.yml").read_text() + GOLANGCI_FORMATTERS)

    def oxlint(self) -> None:
        if not (self.has(OXLINT_CFG) or self.has(ESLINT_CFG) or self.has(BIOME_CFG)):
            self.write(".oxlintrc.json", (DEFAULTS / "oxlintrc.json").read_text())

    def oxfmt(self) -> None:
        # oxfmt formats CSS, SCSS and Less too. CSS needs no lint config: broom's stylelint defaults apply without one.
        if self.has(BIOME_CFG) or self.has(OXFMT_CFG) or self.has(PRETTIER_CFG) or pkg_has_key(self.root, "prettier"):
            return
        oxfmt = shutil.which("oxfmt")
        if oxfmt and not self.dry_run:
            run([oxfmt, "--init"], self.root, timeout=30)
        if not (self.root / ".oxfmtrc.json").exists():
            self.write(".oxfmtrc.json", "{}\n")
        elif not self.dry_run:
            self.actions.append("added .oxfmtrc.json (oxfmt --init)")

    def ruff(self) -> None:
        if ruff_configured(self.root / "_.py", self.root):
            return
        if (self.root / "pyproject.toml").exists():
            self.actions.append("pyproject.toml has no ruff settings; add this under [tool.ruff.lint]:\n"
                                + RUFF_DEFAULT.split("\n", 1)[1])
        else:
            self.write("ruff.toml", RUFF_DEFAULT)

    def swift(self) -> None:
        # Swift needs no lint config either: broom's SwiftLint defaults apply without one.
        if not self.has((SWIFT_FORMAT_CFG, SWIFTFORMAT_CFG)):
            self.write(SWIFT_FORMAT_CFG, SWIFT_FORMAT_DEFAULT)


def add_default_configs(root: Path, langs: Dict[str, List[Path]], *, dry_run: bool) -> List[str]:
    """Add the defaults for the languages `langs` found, and say what was added (or would be, with `dry_run`)."""
    scaffold = Scaffold(root, dry_run=dry_run)
    if "go" in langs:
        scaffold.go()
    if "js" in langs:
        scaffold.oxlint()
    if "js" in langs or "css" in langs:
        scaffold.oxfmt()
    if "py" in langs:
        scaffold.ruff()
    if "swift" in langs:
        scaffold.swift()
    return scaffold.actions
