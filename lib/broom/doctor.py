"""`broom doctor`: which languages a repo has, whether the tools broom needs for them are installed and actually
run, which configs exist, and the pitfalls that break a setup without saying so."""

from __future__ import annotations

import json
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__
from .common import (
    BIOME_CFG, DATA_ROOT, DEFAULTS, ESLINT_CFG, GOLANGCI_CFG, OXFMT_CFG, OXLINT_CFG, PRETTIER_CFG, REPO_FILE, RUFF_CFG,
    SETTINGS,
    find_up, js_formatter, js_linters, load_json, read_jsonc, resolve_bin, ruff_configured, run, save_json,
    short_hash,
)

MARKERS = {"go.mod": "go", "package.json": "js", "tsconfig.json": "js", "Cargo.toml": "rust",
           "pyproject.toml": "py", "setup.py": "py", "requirements.txt": "py"}
SKIP_DIRS = {"node_modules", "vendor", "target", "dist", "build", "out", "venv", "__pycache__", "coverage"}
LANG_NAMES = {"go": "Go", "js": "TS/JS", "rust": "Rust", "py": "Python", "broom": "broom"}
# Plugins that start a language server for the same files as broom's .lsp.json. Claude Code starts only the
# first server registered for an extension, so either one silently never runs.
LSP_PLUGINS = {"gopls-lsp": "go", "gopls": "go", "typescript-lsp": "js", "vtsls": "js", "ts7-lsp": "js",
               "typescript-language-server": "js", "rust-analyzer-lsp": "rust", "rust-analyzer": "rust",
               "pyright-lsp": "py", "pyright": "py"}
LOCKFILES = (("pnpm-lock.yaml", "pnpm"), ("bun.lock", "bun"), ("bun.lockb", "bun"), ("yarn.lock", "yarn"),
             ("package-lock.json", "npm"))
ADD_DEV = {"pnpm": "pnpm add -D", "bun": "bun add -d", "yarn": "yarn add -D", "npm": "npm i -D"}
CONFIG_NAMES = (*GOLANGCI_CFG, *BIOME_CFG, *OXFMT_CFG, *PRETTIER_CFG, *OXLINT_CFG, *ESLINT_CFG, *RUFF_CFG,
                *MARKERS, *(lock for lock, _ in LOCKFILES))
MAX_PROJECTS = 20


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


def tools_db() -> dict:
    return json.loads((DEFAULTS / "tools.json").read_text())


def scan(root: Path, max_depth: int = 3) -> Dict[str, List[Path]]:
    """Project directories per language, from marker files up to `max_depth` below the root."""
    found: Dict[str, List[Path]] = {}
    base = len(root.parts)
    for d, dirs, files in os.walk(root):
        depth = len(Path(d).parts) - base
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")) if depth < max_depth else []
        for name, lang in MARKERS.items():
            projects = found.setdefault(lang, [])
            if name in files and Path(d) not in projects and len(projects) < MAX_PROJECTS:
                projects.append(Path(d))
    return {lang: dirs for lang, dirs in found.items() if dirs}


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


def diagnose(repo: Path, projects: Optional[Dict[str, List[Path]]] = None) -> dict:
    db = tools_db()
    projects = scan(repo) if projects is None else projects
    items: List[Item] = []
    machine: List[Tuple[str, str, str, str]] = []  # (lang, role, tool, name on PATH)

    def rel(p: Path) -> str:
        return "." if p == repo else str(p.relative_to(repo))

    def in_project(p: Path, cmd: str) -> str:
        return cmd if p == repo else f"cd {rel(p)} && {cmd}"

    def dev_fix(item: Item, project: Path, pkg: str) -> Item:
        """Missing JS tools go in as devDependencies, at the repo root when it has a package.json (tools resolve
        from node_modules/.bin up to the root, so one install serves every package), else in the project, else
        globally."""
        target = repo if (repo / "package.json").exists() else project
        if (target / "package.json").exists():
            item.project = rel(target)
            item.dev, item.pm = pkg, add_dev_command(target, repo)
            item.fix = f"{item.pm} {pkg}"
        else:
            item.fix = install_command(db.get(item.tool, {}))
        return item

    def config_home(dirs: List[Path]) -> Path:
        """Where a missing config goes: configs are found by walking up, so one at the root covers a monorepo."""
        return dirs[0] if len(dirs) == 1 else repo

    if "go" in projects:
        machine += [("go", "types", "go", "go"), ("go", "format", "gofmt", "gofmt"),
                    ("go", "lint", "golangci-lint", "golangci-lint"), ("go", "lsp", "gopls", "gopls")]
        for p in projects["go"]:
            cfg = find_up(p, GOLANGCI_CFG, repo)
            items.append(Item("go", "config", "golangci config", "ok", rel(p),
                              f"project {cfg.name}" if cfg else "broom's defaults (no project config)"))

    for p in projects.get("js", []):
        probe_file = p / "_.ts"
        for tool, _ in js_linters(probe_file, repo):
            name = "oxlint" if tool.startswith("oxlint") else tool
            local_only = tool in ("eslint",)
            exe = resolve_bin(name, p, repo, local_only=local_only)
            detail = "broom's defaults (no project config)" if tool == "oxlint-default" else f"project {name} config"
            if exe:
                items.append(Item("js", "lint", name, "ok", rel(p), detail))
            elif tool in ("eslint", "biome"):
                items.append(Item("js", "deps", name, "missing", rel(p),
                                  "configured, but the project's dependencies aren't installed",
                                  in_project(p, f"{package_manager(p, repo)} install")))
            else:
                items.append(dev_fix(Item("js", "lint", "oxlint", "missing", rel(p), detail), p, "oxlint"))
            if tool == "oxlint-default" and find_up(p, ["tsconfig.json"], repo) \
                    and not resolve_bin("tsgolint", p, repo):
                items.append(dev_fix(Item("js", "lint", "tsgolint", "missing", rel(p), "type-aware rules"), p,
                                     "oxlint-tsgolint"))
        fmt = js_formatter(probe_file, repo)
        if fmt is None:
            pass  # reported once for all such projects, below
        elif resolve_bin(fmt[0], p, repo):
            items.append(Item("js", "format", fmt[0], "ok", rel(p), f"project {fmt[0]} config"))
        else:
            items.append(Item("js", "deps", fmt[0], "missing", rel(p),
                              "configured, but the project's dependencies aren't installed",
                              in_project(p, f"{package_manager(p, repo)} install")))
        if (p / "tsconfig.json").exists():
            if resolve_bin("tsc", p, repo):
                items.append(Item("js", "types", "tsc", "ok", rel(p)))
            else:
                items.append(dev_fix(Item("js", "types", "tsc", "missing", rel(p)), p, "typescript"))
    unformatted = [p for p in projects.get("js", []) if js_formatter(p / "_.ts", repo) is None]
    if unformatted:
        home = config_home(unformatted)
        items.append(Item("js", "format", "oxfmt", "off", rel(home),
                          f"no formatter config ({len(unformatted)} project(s)), so broom doesn't format TS/JS",
                          f"broom init {rel(home)}"))
        if not resolve_bin("oxfmt", home, repo):
            items.append(dev_fix(Item("js", "format", "oxfmt", "off", rel(home), "needed once formatting is on"), home,
                                 "oxfmt"))
    if "js" in projects:
        machine.append(("js", "lsp", "tsc", "tsc"))

    if "rust" in projects:
        machine += [("rust", "types", "cargo", "cargo"), ("rust", "format", "rustfmt", "rustfmt"),
                    ("rust", "lint", "cargo-clippy", "cargo"), ("rust", "lsp", "rust-analyzer", "rust-analyzer")]

    if "py" in projects:
        machine += [("py", "lint", "ruff", "ruff"), ("py", "lsp", "pyright-langserver", "pyright-langserver")]
        unformatted = [p for p in projects["py"] if not ruff_configured(p / "_.py", repo)]
        if unformatted:
            home = config_home(unformatted)
            items.append(Item("py", "format", "ruff format", "off", rel(home),
                              f"no ruff config ({len(unformatted)} project(s)), so broom doesn't format Python",
                              f"broom init {rel(home)}"))

    def check_machine(entry: Tuple[str, str, str, str]) -> Item:
        lang, role, tool, name = entry
        spec = db.get(tool, {})
        exe = shutil.which(name)
        if not exe:
            return Item(lang, role, tool, "missing", fix=install_command(spec))
        works, first = probe(exe, spec, repo)
        if not works:
            return Item(lang, role, tool, "broken", detail=first, fix=install_command(spec))
        if tool == "tsc" and role == "lsp":
            m = re.search(r"(\d+)\.\d+", first)
            if m and int(m.group(1)) < 7:
                return Item(lang, role, tool, "broken", detail=f"{first}: the language server needs TypeScript 7 "
                            "(`tsc --lsp`); editors that use typescript-language-server with the global install "
                            "then need a project-local TypeScript", fix=install_command(spec))
        return Item(lang, role, tool, "ok", detail=first)

    with ThreadPoolExecutor(max_workers=6) as pool:
        items += list(pool.map(check_machine, machine))

    for path in settings_files(repo):
        enabled = load_json(path, {}).get("enabledPlugins") or {}
        for key, on in enabled.items():
            lang = LSP_PLUGINS.get(key.split("@")[0])
            if on is True and lang in projects:
                items.append(Item(lang, "plugin", key, "conflict", "",
                                  f"also starts a {LANG_NAMES[lang]} language server; only the first one "
                                  "registered for an extension runs", f"claude plugin disable {key}"))

    items += check_repo_file(repo)
    unique: Dict[Tuple[str, ...], Item] = {}
    for i in items:  # one package's missing tool installed at the root is the same fix for every package
        unique.setdefault((i.lang, i.role, i.tool, i.status, i.project, i.fix), i)
    items = list(unique.values())
    fixes, configure = plan_commands(items)
    return {
        "version": __version__, "repo": str(repo),
        "languages": {lang: [rel(p) for p in dirs] for lang, dirs in projects.items()},
        "items": [asdict(i) for i in items],
        "fix": fixes, "configure": configure,
        "healthy": all(i.status == "ok" for i in items),
    }


def check_repo_file(repo: Path) -> List[Item]:
    """The repo's .broom.json: values broom would otherwise ignore without a word."""
    path = repo / REPO_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(re.sub(r"^\s*//.*$", "", path.read_text(), flags=re.M))
    except (OSError, ValueError):
        return [Item("broom", "config", REPO_FILE, "broken", ".", "not valid JSON, so broom ignores it")]
    if not isinstance(data, dict):
        return [Item("broom", "config", REPO_FILE, "broken", ".", "must be a JSON object")]
    problems = [f"{k}: {data[k]!r} is not one of {', '.join(SETTINGS[k][1])}" for k in SETTINGS
                if k in data and str(data[k]).lower() not in SETTINGS[k][1]]
    unknown = [k for k in data if k not in SETTINGS and k != "exclude"]
    if unknown:
        problems.append("unknown key(s): " + ", ".join(unknown))
    if "exclude" in data and not isinstance(data["exclude"], list):
        problems.append("exclude must be a list of globs")
    if problems:
        return [Item("broom", "config", REPO_FILE, "broken", ".", "; ".join(problems))]
    shown = ", ".join(f"{k}={data[k]}" for k in SETTINGS if k in data)
    excl = f"{len(data.get('exclude', []))} exclude pattern(s)" if data.get("exclude") else ""
    return [Item("broom", "config", REPO_FILE, "ok", ".", ", ".join(x for x in (shown, excl) if x) or "empty")]


def plan_commands(items: List[Item]) -> Tuple[List[str], List[str]]:
    """Shell commands in order: `fix` for missing/broken tools and conflicts, `configure` for configs that are
    off. devDependencies for one project share a command; brew formulae share one `brew install`."""
    buckets: Dict[str, List[str]] = {"fix": [], "configure": []}
    dev: Dict[Tuple[str, str, str], List[str]] = {}
    brew: Dict[str, List[str]] = {"fix": [], "configure": []}
    for i in items:
        if i.status == "ok":
            continue
        bucket = "configure" if i.status == "off" else "fix"
        if i.dev:
            pkgs = dev.setdefault((bucket, i.project, i.pm), [])
            if i.dev not in pkgs:
                pkgs.append(i.dev)
        elif i.fix.startswith("brew install ") and "&&" not in i.fix:
            brew[bucket] += [f for f in i.fix.split()[2:] if f not in brew[bucket]]
        elif i.fix and i.fix not in buckets[bucket]:
            buckets[bucket].append(i.fix)
    for bucket in buckets:
        if brew[bucket]:
            buckets[bucket].insert(0, "brew install " + " ".join(brew[bucket]))
    for (bucket, project, pm), pkgs in dev.items():
        cmd = f"{pm} {' '.join(pkgs)}"
        buckets[bucket].append(cmd if project in ("", ".") else f"cd {project} && {cmd}")
    return buckets["fix"], buckets["configure"]


def cache_key(repo: Path, projects: Dict[str, List[Path]]) -> str:
    """Changes when a tool is installed or removed (PATH directories change mtime), a config or lockfile
    changes, or Claude Code's settings change."""
    parts: List[object] = [__version__, str(repo), os.environ.get("PATH", "")]
    paths = [Path(d) for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    paths += settings_files(repo)
    for dirs in projects.values():
        for p in dirs:
            paths += [p / n for n in CONFIG_NAMES] + [p / "node_modules" / ".bin"]
    for p in paths:
        try:
            parts.append(p.stat().st_mtime)
        except OSError:
            parts.append(None)
    return short_hash(json.dumps(parts))


def diagnose_cached(repo: Path) -> dict:
    projects = scan(repo)
    key = cache_key(repo, projects)
    path = DATA_ROOT / "doctor" / f"{short_hash(str(repo))}.json"
    cached = load_json(path, {})
    if cached.get("key") == key:
        return cached["result"]
    result = diagnose(repo, projects)
    save_json(path, {"key": key, "result": result})
    return result


def gaps(result: dict) -> List[dict]:
    return [i for i in result["items"] if i["status"] != "ok"]


def gaps_hash(result: dict) -> str:
    return short_hash(json.dumps(sorted((i["tool"], i["status"], i["project"]) for i in gaps(result))))


def describe(i: dict) -> str:
    where = f" in {i['project']}" if i["project"] not in ("", ".") else ""
    if i["status"] == "off":
        return f"{LANG_NAMES[i['lang']]} formatting is off{where} (no config)"
    if i["status"] == "conflict":
        return f"plugin {i['tool']} conflicts with broom's {LANG_NAMES[i['lang']]} language server"
    if i["role"] == "deps":
        return f"{i['tool']} is configured{where} but the project's dependencies aren't installed"
    return f"{i['tool']} {i['status']} ({LANG_NAMES[i['lang']]} {i['role']}{where})"


MARKS = {"ok": "✓", "missing": "✗", "broken": "✗", "off": "○", "conflict": "⚠"}


def render_text(result: dict) -> str:
    repo = result["repo"]
    home = str(Path.home())
    out = [f"broom doctor: {'~' + repo[len(home):] if repo.startswith(home) else repo}"]
    langs = ", ".join(f"{LANG_NAMES[lang]} ({len(dirs)} project{'s' if len(dirs) > 1 else ''})"
                      for lang, dirs in result["languages"].items())
    out.append(f"Languages: {langs or 'none found'}\n")
    for i in result["items"]:
        where = f"  [{i['project']}]" if i["project"] not in ("", ".") else ""
        detail = f"  {i['detail']}" if i["detail"] else ""
        out.append(f"  {MARKS[i['status']]} {LANG_NAMES[i['lang']]:<6} {i['role']:<6} {i['tool']:<20}"
                   f"{i['status'] if i['status'] != 'ok' else ''}{detail}{where}".rstrip())
    if result["fix"]:
        out.append("\nTo fix:\n" + "\n".join(f"  {c}" for c in result["fix"]))
    if result["configure"]:
        out.append("\nTo turn formatting on:\n" + "\n".join(f"  {c}" for c in result["configure"]))
    if result["healthy"]:
        out.append("\nAll set.")
    return "\n".join(out)


# ---------------------------------------------------------------- setup state

SETUP_STATE = DATA_ROOT / "setup.json"


def record_setup(repo: Path, status: str) -> dict:
    """Remember that the user set up (`done`) or declined (`dismissed`) with the gaps this repo has now. broom
    doesn't raise the setup again until the gaps change."""
    result = diagnose_cached(repo)
    state = load_json(SETUP_STATE, {})
    state[str(repo)] = {"status": status, "gaps": gaps_hash(result)}
    save_json(SETUP_STATE, state)
    return result


def needs_setup(repo: Path, result: dict) -> bool:
    if not gaps(result):
        return False
    return load_json(SETUP_STATE, {}).get(str(repo), {}).get("gaps") != gaps_hash(result)
