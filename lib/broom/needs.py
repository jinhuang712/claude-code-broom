"""What each language in a repo needs and has: the tools, whether they run, the project configs, the language
server, and plugins that start a second server for the same files. `broom doctor` reports it; a Diagnosis builds
it one language at a time."""

from __future__ import annotations

import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from .common import (
    DEFAULTS, DIALECT_DEFAULTS, GOLANGCI_CFG, SWIFT_FORMAT_CFG, SWIFTFORMAT_CFG, SWIFTLINT_CFG, css_linters, find_up,
    in_node_modules, js_formatter, js_linters, load_json, read_jsonc, resolve_bin, ruff_configured, run, setting,
    swift_format_cmd, swift_formatter, swift_linter,
)

LANG_NAMES = {"go": "Go", "js": "TS/JS", "rust": "Rust", "py": "Python", "css": "CSS", "scss": "SCSS",
              "less": "Less", "swift": "Swift", "broom": "broom"}
# Plugins that start a language server for the same files as broom's .lsp.json. Claude Code starts only the
# first server registered for an extension, so either one silently never runs.
LSP_PLUGINS = {"gopls-lsp": "go", "gopls": "go", "typescript-lsp": "js", "vtsls": "js", "ts7-lsp": "js",
               "typescript-language-server": "js", "rust-analyzer-lsp": "rust", "rust-analyzer": "rust",
               "pyright-lsp": "py", "pyright": "py", "swift-lsp": "swift", "sourcekit-lsp": "swift"}
LOCKFILES = (("pnpm-lock.yaml", "pnpm"), ("bun.lock", "bun"), ("bun.lockb", "bun"), ("yarn.lock", "yarn"),
             ("package-lock.json", "npm"))
ADD_DEV = {"pnpm": "pnpm add -D", "bun": "bun add -d", "yarn": "yarn add -D", "npm": "npm i -D"}
DEFAULTS_DETAIL = "broom's defaults (no project config)"
DEPS_DETAIL = "configured, but the project's dependencies aren't installed"
Machine = Tuple[str, str, str, str]  # a tool on PATH to probe: (lang, role, tool, name on PATH)


@dataclass
class Item:
    lang: str
    role: str  # format, lint, types, lsp, plugin or deps
    tool: str
    status: str  # ok, missing, broken, off (a config is missing so broom stays hands-off) or conflict
    project: str = ""  # directory for project-local tools and configs; "" for machine-wide ones
    detail: str = ""
    fix: str = ""  # shell command that fixes it
    dev: str = ""  # devDependency the fix adds, so fixes for one project can share one install command
    pm: str = ""  # the project's add-a-devDependency command
    global_fix: str = ""  # for a devDependency fix: the machine-wide install, which serves every repo


def tools_db() -> dict:
    return json.loads((DEFAULTS / "tools.json").read_text())


def package_manager(project: Path, stop: Path) -> str:
    for lock, pm in LOCKFILES:
        if find_up(project, [lock], stop):
            return pm
    return "npm"


def add_dev_command(project: Path, stop: Path) -> str:
    pm = package_manager(project, stop)
    cmd = ADD_DEV[pm]
    if pm == "pnpm" and (project / "pnpm-workspace.yaml").exists():
        cmd += " -w"  # pnpm refuses to add to a workspace root without it
    elif pm == "yarn" and "workspaces" in read_jsonc(project / "package.json"):
        cmd += " -W"
    return cmd


def install_command(spec: dict) -> str:
    options = spec.get("install") or []
    for manager, cmd in options:
        if shutil.which(manager):
            return cmd
    return options[0][1] if options else ""


def probe(exe: str, spec: dict, cwd: Path) -> Tuple[bool, str]:
    """(runs, first line of its output). A rustup proxy without its component exists on PATH but fails here."""
    cmd = spec.get("probe")
    if not cmd:
        return True, ""
    rc, out, err = run([exe, *cmd[1:]], cwd, timeout=20)
    first = next((r.strip() for r in (out + "\n" + err).splitlines() if r.strip()), "")
    return rc == 0, first[:120]


def settings_files(repo: Path) -> List[Path]:
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return [config / "settings.json", repo / ".claude" / "settings.json", repo / ".claude" / "settings.local.json"]


def swift_format_version(cwd: Path) -> str:
    """swift-format's version; "" when neither a standalone install nor the toolchain's (Swift 6 and later) runs."""
    cmd = swift_format_cmd()
    if not cmd:
        return ""
    rc, out, _ = run([*cmd, "--version"], cwd, timeout=20)
    return out.strip() if rc == 0 else ""


class Diagnosis:
    """The findings for one repo's languages (`projects`: language to project directories), and the tools on PATH
    they need, probed at the end in parallel."""

    def __init__(self, repo: Path, projects: Dict[str, List[Path]]) -> None:
        self.repo, self.projects, self.db = repo, projects, tools_db()
        self.items: List[Item] = []
        self.machine: List[Machine] = []

    def findings(self) -> List[Item]:
        steps: List[Callable[[], None]] = [self.go, self.js, self.rust, self.py, self.css_lint, self.css_dialects,
                                           self.css_format, self.smells, self.swift]
        for step in steps:
            step()
        with ThreadPoolExecutor(max_workers=6) as pool:
            self.items += list(pool.map(self.check_machine, self.machine))
        self.plugins()
        return self.items

    # helpers

    def rel(self, p: Path) -> str:
        return "." if p == self.repo else str(p.relative_to(self.repo))

    def deps_missing(self, lang: str, name: str, d: Path) -> Item:
        cmd = f"{package_manager(d, self.repo)} install"
        return Item(lang, "deps", name, "missing", self.rel(d), DEPS_DETAIL,
                    cmd if d == self.repo else f"cd {self.rel(d)} && {cmd}")

    def dev_fix(self, item: Item, project: Path, pkg: str) -> Item:
        """Missing JS tools go in as devDependencies, at the repo root when it has a package.json (tools resolve
        from node_modules/.bin up to the root, so one install serves every package), else in the project, else
        globally."""
        target = self.repo if (self.repo / "package.json").exists() else project
        global_fix = install_command(self.db.get(item.tool, {}))
        if (target / "package.json").exists():
            item.project = self.rel(target)
            item.dev, item.pm = pkg, add_dev_command(target, self.repo)
            item.fix, item.global_fix = f"{item.pm} {pkg}", global_fix
        else:
            item.fix = global_fix
        return item

    def formatting_off(self, lang: str, tool: str, dirs: List[Path], what: str, label: str) -> Path:
        """One item for every project without a formatter config, at the config's home: configs are found by
        walking up, so one at the root covers a monorepo. The home, for a fix that installs the formatter."""
        home = dirs[0] if len(dirs) == 1 else self.repo
        self.items.append(Item(lang, "format", tool, "off", self.rel(home),
                               f"no {what} config ({len(dirs)} project(s)), so broom doesn't format {label}",
                               f"broom init {self.rel(home)}"))
        return home

    def oxfmt_needed(self, lang: str, home: Path) -> None:
        if not resolve_bin("oxfmt", home, self.repo):
            self.items.append(self.dev_fix(Item(lang, "format", "oxfmt", "off", self.rel(home),
                                                "needed once formatting is on"), home, "oxfmt"))

    def check_machine(self, entry: Machine) -> Item:
        lang, role, tool, name = entry
        spec = self.db.get(tool, {})
        exe = shutil.which(name)
        if not exe:
            return Item(lang, role, tool, "missing", fix=install_command(spec))
        works, first = probe(exe, spec, self.repo)
        if not works:
            return Item(lang, role, tool, "broken", detail=first, fix=install_command(spec))
        return Item(lang, role, tool, "ok", detail=first if spec.get("probe_is_version", True) else "")

    # languages

    def go(self) -> None:
        if "go" not in self.projects:
            return
        self.machine += [("go", "types", "go", "go"), ("go", "format", "gofmt", "gofmt"),
                         ("go", "lint", "golangci-lint", "golangci-lint"), ("go", "lsp", "gopls", "gopls")]
        for p in self.projects["go"]:
            cfg = find_up(p, GOLANGCI_CFG, self.repo)
            self.items.append(Item("go", "config", "golangci config", "ok", self.rel(p),
                                   f"project {cfg.name}" if cfg else DEFAULTS_DETAIL))

    def js(self) -> None:
        for p in self.projects.get("js", []):
            self.js_lint(p)
            self.js_format(p)
            if (p / "tsconfig.json").exists():
                ok = resolve_bin("tsc", p, self.repo)
                self.items.append(Item("js", "types", "tsc", "ok", self.rel(p)) if ok else
                                  self.dev_fix(Item("js", "types", "tsc", "missing", self.rel(p)), p, "typescript"))
        unformatted = [p for p in self.projects.get("js", []) if js_formatter(p / "_.ts", self.repo) is None]
        if unformatted:
            self.oxfmt_needed("js", self.formatting_off("js", "oxfmt", unformatted, "formatter", "TS/JS"))
        if "js" in self.projects:
            self.items.append(typescript_lsp(self.repo, self.db))

    def js_lint(self, p: Path) -> None:
        for tool, _ in js_linters(p / "_.ts", self.repo):
            name = "oxlint" if tool.startswith("oxlint") else tool
            detail = DEFAULTS_DETAIL if tool == "oxlint-default" else f"project {name} config"
            if resolve_bin(name, p, self.repo, local_only=tool == "eslint"):
                self.items.append(Item("js", "lint", name, "ok", self.rel(p), detail))
            elif tool in ("eslint", "biome"):
                self.items.append(self.deps_missing("js", name, p))
            else:
                self.items.append(self.dev_fix(Item("js", "lint", "oxlint", "missing", self.rel(p), detail), p,
                                               "oxlint"))
            if tool == "oxlint-default" and find_up(p, ["tsconfig.json"], self.repo) \
                    and not resolve_bin("tsgolint", p, self.repo):
                self.items.append(self.dev_fix(Item("js", "lint", "tsgolint", "missing", self.rel(p),
                                                    "type-aware rules"), p, "oxlint-tsgolint"))

    def js_format(self, p: Path) -> None:
        fmt = js_formatter(p / "_.ts", self.repo)
        if fmt is None:
            return  # reported once for all such projects
        if resolve_bin(fmt[0], p, self.repo):
            self.items.append(Item("js", "format", fmt[0], "ok", self.rel(p), f"project {fmt[0]} config"))
        else:
            self.items.append(self.deps_missing("js", fmt[0], p))

    def rust(self) -> None:
        if "rust" in self.projects:
            self.machine += [("rust", "types", "cargo", "cargo"), ("rust", "format", "rustfmt", "rustfmt"),
                             ("rust", "lint", "cargo-clippy", "cargo"),
                             ("rust", "lsp", "rust-analyzer", "rust-analyzer")]

    def py(self) -> None:
        if "py" not in self.projects:
            return
        self.machine += [("py", "lint", "ruff", "ruff"), ("py", "lsp", "pyright-langserver", "pyright-langserver")]
        unformatted = [p for p in self.projects["py"] if not ruff_configured(p / "_.py", self.repo)]
        if unformatted:
            self.formatting_off("py", "ruff format", unformatted, "ruff", "Python")

    def css_lint(self) -> None:
        for p in self.projects.get("css", []):
            for tool, d in css_linters(p / "_.css", self.repo):
                name = "stylelint" if tool.startswith("stylelint") else tool
                if tool == "stylelint-default":
                    item = Item("css", "lint", name, "ok", self.rel(d), DEFAULTS_DETAIL)
                    if not resolve_bin("stylelint", d, self.repo):
                        item.status = "missing"
                        item = self.dev_fix(item, d, "stylelint")
                    self.items.append(item)
                elif resolve_bin(name, d, self.repo, local_only=name == "eslint"):
                    self.items.append(Item("css", "lint", name, "ok", self.rel(d), f"project {name} config"))
                else:
                    self.items.append(self.deps_missing("css", name, d))

    def css_format(self) -> None:
        """CSS in a JS project is formatted (or not) along with it; this is CSS elsewhere, as in a Go service's
        static/."""
        unformatted = [p for p in self.projects.get("css", [])
                       if p not in self.projects.get("js", []) and js_formatter(p / "_.css", self.repo) is None]
        if unformatted:
            self.oxfmt_needed("css", self.formatting_off("css", "oxfmt", unformatted, "formatter", "CSS"))
        if "css" in self.projects:
            self.machine.append(("css", "lsp", "vscode-css-language-server", "vscode-css-language-server"))

    def css_dialects(self) -> None:
        """SCSS and Less with broom's stylelint defaults need the dialect's config installed in the project."""
        for ext, (dialect, pkg) in DIALECT_DEFAULTS.items():
            lang = ext[1:]
            for p in self.projects.get(lang, []):
                for tool, d in css_linters(p / f"_{ext}", self.repo):
                    if tool != "stylelint-default" or in_node_modules(pkg, d, self.repo):
                        continue
                    item = Item(lang, "lint", pkg, "missing", self.rel(d), f"broom's {dialect} defaults")
                    if (self.repo / "package.json").exists() or (d / "package.json").exists():
                        self.items.append(self.dev_fix(item, d, pkg))
                    else:  # stylelint loads it from the project, so a global install wouldn't do
                        item.detail += ": stylelint loads it from node_modules, so this needs a package.json"
                        self.items.append(item)

    def smells(self) -> None:
        coded = [lang for lang in ("go", "js", "py", "swift") if lang in self.projects]
        if coded and setting("smells", self.repo) != "off":  # duplicate code, in every language smells measure
            self.machine.append((coded[0], "smells", "jscpd", "jscpd"))

    def swift(self) -> None:
        swift = self.projects.get("swift") or []
        if not swift:
            return
        self.machine += [("swift", "lint", "swiftlint", "swiftlint"),
                         ("swift", "lsp", "sourcekit-lsp", "sourcekit-lsp")]
        if any((p / "Package.swift").exists() for p in swift):  # Xcode projects aren't built
            self.machine.append(("swift", "types", "swift", "swift"))
        version = swift_format_version(self.repo)
        for p in swift:
            tool, d = swift_linter(p / "_.swift", self.repo)
            detail = f"project {SWIFTLINT_CFG}" if tool == "swiftlint" else DEFAULTS_DETAIL
            self.items.append(Item("swift", "config", "swiftlint config", "ok", self.rel(d), detail))
            self.swift_format(p, version)
        unformatted = [p for p in swift if swift_formatter(p / "_.swift", self.repo) is None]
        if unformatted:
            self.formatting_off("swift", "swift-format", unformatted, "formatter", "Swift")
            if not version:  # the toolchain has it from Swift 6
                self.items.append(Item("swift", "format", "swift-format", "off", detail="needed once formatting is on",
                                       fix=install_command(self.db.get("swift-format", {}))))

    def swift_format(self, p: Path, version: str) -> None:
        """A project's Swift formatter: SwiftFormat on PATH, or swift-format, standalone or the toolchain's."""
        fmt = swift_formatter(p / "_.swift", self.repo)
        if fmt is None:
            return  # reported once for all such projects
        tool, d = fmt
        cfg = SWIFTFORMAT_CFG if tool == "swiftformat" else SWIFT_FORMAT_CFG
        if shutil.which(tool) if tool == "swiftformat" else version:
            self.items.append(Item("swift", "format", tool, "ok", self.rel(d), f"project {cfg}"))
        else:
            self.items.append(Item("swift", "format", tool, "missing", detail=f"the project's {cfg} needs it",
                                   fix=install_command(self.db.get(tool, {}))))

    def plugins(self) -> None:
        for path in settings_files(self.repo):
            enabled = load_json(path, {}).get("enabledPlugins") or {}
            for key, on in enabled.items():
                lang = LSP_PLUGINS.get(key.split("@")[0])
                if on is True and lang in self.projects:
                    self.items.append(Item(lang, "plugin", key, "conflict", "",
                                           f"also starts a {LANG_NAMES[lang]} language server; only the first one "
                                           "registered for an extension runs", f"claude plugin disable {key}"))


def typescript_lsp(repo: Path, db: dict) -> Item:
    """The TypeScript server broom's launcher starts for this repo. Claude Code starts one per session, from the
    repo root, so that is where it's decided."""
    from .lsp import typescript_server

    cmd, why = typescript_server(repo)
    tool = "typescript-language-server"
    if cmd and Path(cmd[0]).name == tool:
        return Item("js", "lsp", tool, "ok", detail=why)
    detail = f"without it the language server is {why}" if cmd else why
    return Item("js", "lsp", tool, "missing", detail=detail, fix=install_command(db.get(tool, {})))
