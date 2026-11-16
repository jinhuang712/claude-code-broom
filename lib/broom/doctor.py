"""`broom doctor`: which languages a repo has, whether the tools broom needs for them are installed and actually
run, which configs exist, and the pitfalls that break a setup without saying so."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__
from .config import DEAD_CODE, LIMIT_PAIR, REPO_FILE, SETTINGS, SMELL_LIMITS, SMELL_PRESENCE, repo_file
from .gitutil import git
from .needs import LANG_NAMES, LOCKFILES, Diagnosis, Item, settings_files
from .state import DATA_ROOT, load_json, save_json, short_hash, update_json
from .toolchain import (
    BIOME_CFG, DIALECT_DEFAULTS, ESLINT_CFG, GOLANGCI_CFG, OXFMT_CFG, OXLINT_CFG, PRETTIER_CFG, RUFF_CFG,
    STYLELINT_CFG, SWIFT_FORMAT_CFG, SWIFTFORMAT_CFG, SWIFTLINT_CFG, find_up,
)

MARKERS = {"go.mod": "go", "package.json": "js", "tsconfig.json": "js", "Cargo.toml": "rust",
           "pyproject.toml": "py", "setup.py": "py", "requirements.txt": "py"}
SKIP_DIRS = {"node_modules", "vendor", "target", "dist", "build", "out", "venv", "__pycache__", "coverage", "Pods",
             "Carthage", "DerivedData"}
CONFIG_NAMES = (*GOLANGCI_CFG, *BIOME_CFG, *OXFMT_CFG, *PRETTIER_CFG, *OXLINT_CFG, *ESLINT_CFG, *RUFF_CFG,
                *STYLELINT_CFG, SWIFTLINT_CFG, SWIFT_FORMAT_CFG, SWIFTFORMAT_CFG, "Package.swift", *MARKERS,
                *(lock for lock, _ in LOCKFILES))
MAX_PROJECTS = 20


def scan(root: Path, max_depth: int = 3) -> Dict[str, List[Path]]:
    """Project directories per language, from marker files up to `max_depth` below the root, and CSS's and Swift's."""
    found: Dict[str, List[Path]] = {}
    base = len(root.parts)
    for d, dirs, files in os.walk(root):
        depth = len(Path(d).parts) - base
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")) if depth < max_depth else []
        for name, lang in MARKERS.items():
            projects = found.setdefault(lang, [])
            if name in files and Path(d) not in projects and len(projects) < MAX_PROJECTS:
                projects.append(Path(d))
    found.update(tracked_projects(root))
    return {lang: dirs for lang, dirs in found.items() if dirs}


def tracked_projects(root: Path) -> Dict[str, List[Path]]:
    """`css`, plus `scss` and `less` for those dialects, and `swift`: the projects holding such files, a CSS file's
    being its nearest package.json and a Swift file's its nearest Package.swift, else the root. Neither language
    has a project file to find everywhere (an Xcode app has no Package.swift), so this goes by the files git tracks,
    at any depth; generated and vendored ones don't count. Untracked files would need a walk of the working tree:
    160 ms instead of 25 on a 6,000-file repo, too slow for SessionStart."""
    out = git(["ls-files", "--cached", "--", "*.css", "*.scss", "*.less", "*.swift"], root) or ""
    homes: Dict[Tuple[Path, str], Path] = {}
    found: Dict[str, List[Path]] = {"css": [], "scss": [], "less": [], "swift": []}
    for name in out.splitlines():
        rel = Path(name)
        if name.endswith(".min.css") or any(p in SKIP_DIRS or p.startswith(".") for p in rel.parts[:-1]):
            continue
        d = (root / rel).parent
        marker = "Package.swift" if rel.suffix == ".swift" else "package.json"
        if (d, marker) not in homes:
            project = find_up(d, [marker], root)
            homes[d, marker] = project.parent if project else root
        if rel.suffix == ".swift":
            langs: Tuple[str, ...] = ("swift",)
        else:
            langs = ("css", rel.suffix[1:]) if rel.suffix in DIALECT_DEFAULTS else ("css",)
        for lang in langs:
            if homes[d, marker] not in found[lang] and len(found[lang]) < MAX_PROJECTS:
                found[lang].append(homes[d, marker])
    return found


def diagnose(repo: Path, projects: Optional[Dict[str, List[Path]]] = None) -> dict:
    """Everything `broom doctor` reports for the repo, and the commands that fix it."""
    projects = scan(repo) if projects is None else projects
    unique: Dict[Tuple[str, ...], Item] = {}
    for i in Diagnosis(repo, projects).findings() + check_repo_file(repo):
        # one package's missing tool installed at the root is the same fix for every package
        unique.setdefault((i.lang, i.role, i.tool, i.status, i.project, i.fix), i)
    items = list(unique.values())
    fixes, configure = plan_commands(items)
    fixes_global, configure_global = plan_commands(items, machine_wide=True)
    return {
        "version": __version__, "repo": str(repo),
        "languages": {lang: ["." if p == repo else str(p.relative_to(repo)) for p in dirs]
                      for lang, dirs in projects.items()},
        "items": [asdict(i) for i in items],
        "fix": fixes, "configure": configure,
        # the same, with JS tools installed machine-wide instead of as devDependencies: once for every repo
        "fix_global": fixes_global, "configure_global": configure_global,
        "healthy": all(i.status == "ok" for i in items),
    }


def limit_problems(limits: object, key: str = "limits") -> List[str]:
    """.broom.json `limits` or `test_limits`: {"function_lines": [soft, hard], ...} with known names and
    soft <= hard."""
    if limits is None:
        return []
    if not isinstance(limits, dict):
        return [f"{key} must be an object of [soft, hard] pairs"]
    out = [f"{key}: unknown name {k}" for k in limits if k not in SMELL_LIMITS]
    for k, pair in limits.items():
        ok = isinstance(pair, list) and len(pair) == LIMIT_PAIR and all(isinstance(n, int) for n in pair)
        if k in SMELL_LIMITS and not (ok and pair[0] <= pair[1]):
            out.append(f"{key}: {k} must be [soft, hard] with soft <= hard")
    return out


REPO_KEYS = ("exclude", "legacy", "limits", "test_limits", "smells_off")  # beside the settings


def check_repo_file(repo: Path) -> List[Item]:
    """The repo's .broom.json: values broom would otherwise ignore without a word, and where it comes from."""
    path = repo_file(repo)
    if path is None:
        return []
    try:
        data = json.loads(re.sub(r"^\s*//.*$", "", path.read_text(), flags=re.M))
    except (OSError, ValueError):
        return [Item("broom", "config", REPO_FILE, "broken", ".", "not valid JSON, so broom ignores it")]
    if not isinstance(data, dict):
        return [Item("broom", "config", REPO_FILE, "broken", ".", "must be a JSON object")]
    problems = [f"{k}: {data[k]!r} is not one of {', '.join(SETTINGS[k][1])}" for k in SETTINGS
                if k in data and str(data[k]).lower() not in SETTINGS[k][1]]
    unknown = [k for k in data if k not in SETTINGS and k not in REPO_KEYS]
    if unknown:
        problems.append("unknown key(s): " + ", ".join(unknown))
    problems += [f"{k} must be a list of globs" for k in ("exclude", "legacy")
                 if k in data and not isinstance(data[k], list)]
    problems += limit_problems(data.get("limits")) + limit_problems(data.get("test_limits"), "test_limits")
    off = data.get("smells_off", [])
    names = set(SMELL_LIMITS) | set(SMELL_PRESENCE) | {DEAD_CODE}
    if not isinstance(off, list) or not all(n in names for n in off):
        problems.append(f"smells_off must list smell names from: {', '.join(sorted(names))}")
    if problems:
        return [Item("broom", "config", REPO_FILE, "broken", ".", "; ".join(problems))]
    shown = [f"{k}={data[k]}" for k in SETTINGS if k in data]
    shown += [f"{len(data['exclude'])} exclude pattern(s)"] if data.get("exclude") else []
    shown += [f"{len(data['legacy'])} legacy pattern(s)"] if data.get("legacy") else []
    shown += [f"limits for {', '.join(data['limits'])}"] if data.get("limits") else []
    shown += [f"test limits for {', '.join(data['test_limits'])}"] if data.get("test_limits") else []
    shown += [f"smells off: {', '.join(data['smells_off'])}"] if data.get("smells_off") else []
    shown += ["read from the main worktree, as this one has none"] if path.parent != repo else []
    if git(["check-ignore", "-q", str(path)], path.parent) is not None:
        shown.append("ignored by git, so clones don't get it and worktrees read the main worktree's")
    return [Item("broom", "config", REPO_FILE, "ok", ".", ", ".join(shown) or "empty")]


def _append_new(items: List[str], item: str) -> None:
    if item not in items:
        items.append(item)


class _Commands:
    """The shell commands that fix or configure what the items lack. devDependencies for one project share a
    command, and brew formulae share one `brew install`."""

    def __init__(self, *, machine_wide: bool) -> None:
        self.machine_wide = machine_wide
        self.buckets: Dict[str, List[str]] = {"fix": [], "configure": []}
        self.dev: Dict[Tuple[str, str, str], List[str]] = {}
        self.brew: Dict[str, List[str]] = {"fix": [], "configure": []}

    def add(self, i: Item) -> None:
        bucket = "configure" if i.status == "off" else "fix"
        if self.machine_wide and i.global_fix:
            _append_new(self.buckets[bucket], i.global_fix)
        elif i.dev:
            _append_new(self.dev.setdefault((bucket, i.project, i.pm), []), i.dev)
        elif i.fix.startswith("brew install ") and "&&" not in i.fix:
            self.brew[bucket] += [f for f in i.fix.split()[2:] if f not in self.brew[bucket]]
        elif i.fix:
            _append_new(self.buckets[bucket], i.fix)

    def ordered(self) -> Tuple[List[str], List[str]]:
        """The `fix` commands and the `configure` ones, the brew install first and the per-project ones last."""
        for bucket in self.buckets:
            if self.brew[bucket]:
                self.buckets[bucket].insert(0, "brew install " + " ".join(self.brew[bucket]))
        for (bucket, project, pm), pkgs in self.dev.items():
            cmd = f"{pm} {' '.join(pkgs)}"
            self.buckets[bucket].append(cmd if project in ("", ".") else f"cd {project} && {cmd}")
        return self.buckets["fix"], self.buckets["configure"]


def plan_commands(items: List[Item], *, machine_wide: bool = False) -> Tuple[List[str], List[str]]:
    """Shell commands in order: `fix` for missing/broken tools and conflicts, `configure` for configs that are
    off. With `machine_wide`, JS tools get their global install instead of a devDependency."""
    commands = _Commands(machine_wide=machine_wide)
    for i in items:
        if i.status != "ok":
            commands.add(i)
    return commands.ordered()


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
        out.append(f"  {MARKS[i['status']]} {LANG_NAMES[i['lang']]:<6} {i['role']:<6} {i['tool']:<20} "
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
ANSWERED = "answered"  # key in setup.json; every other key is a repo path


def gap_kind(i: dict) -> str:
    """A gap without its repo or project: what the user's answer to it applies to, in every repo."""
    return ":".join((i["lang"], i["role"], i["tool"], i["status"]))


def record_setup(repo: Path, status: str) -> dict:
    """Remember that the user set up (`done`) or declined (`dismissed`) with the gaps this repo has now. The
    gaps left are remembered by kind for every repo: broom raises setup again only for a kind of gap the user
    hasn't answered yet, anywhere."""
    result = diagnose_cached(repo)
    def answer(state: dict) -> None:
        state[str(repo)] = {"status": status, "gaps": gaps_hash(result)}
        state[ANSWERED] = sorted(set(state.get(ANSWERED) or []) | {gap_kind(i) for i in gaps(result)})

    update_json(SETUP_STATE, {}, answer)
    return result


def reset_setup() -> int:
    """Forget every setup answer, in every repo. Returns how many kinds of gap were remembered."""
    count = len(load_json(SETUP_STATE, {}).get(ANSWERED) or [])
    save_json(SETUP_STATE, {})
    return count


def answered_kinds() -> set:
    return set(load_json(SETUP_STATE, {}).get(ANSWERED) or [])


def new_gaps(repo: Path, result: dict) -> List[dict]:
    """The gaps setup should raise: none once this repo's gaps were answered as they are, else those of a kind
    not answered in any repo."""
    found = gaps(result)
    if not found or load_json(SETUP_STATE, {}).get(str(repo), {}).get("gaps") == gaps_hash(result):
        return []
    known = answered_kinds()
    return [i for i in found if gap_kind(i) not in known]

