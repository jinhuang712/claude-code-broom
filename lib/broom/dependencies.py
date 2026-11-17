"""The packages a project declares and nothing imports, from the tool each ecosystem has for it: knip (TS/JS), deptry
(Python), cargo-machete (Rust) and `go mod tidy -diff` (Go, 1.23 or later, which needs no install). Each is used only
when it is installed: one that isn't is named once with its install command and never asked for, one that fails is
said with its first error line. They are too slow and too uncertain for a hook, so only `broom diagnose` runs them,
and without a time cut; this module reads the repo's projects and no network (Go gets GOPROXY=off)."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .config import glob_matcher, repo_config
from .gitutil import run
from .needs import LANG_NAMES, install_command, tools_db
from .state import read_jsonc
from .toolchain import resolve_bin

RUN_SECONDS = 300  # what one tool may take: diagnose has no time cut, but a tool that hangs gives no answer
OK_CODES = (0, 1)  # the exit codes of a tool that ran: 1 is "found something" in all four
FIRST_LINE_CHARS = 200
GO_TIDY_DIFF = (1, 23)  # the Go version that has `go mod tidy -diff`
MARKERS = {"js": ("package.json",), "py": ("pyproject.toml", "requirements.txt"), "rust": ("Cargo.toml",),
           "go": ("go.mod",)}
# deptry reports 5 kinds of violation; only DEP002, a declared dependency nothing imports, is this module's.
DEPTRY_OTHERS = "DEP001,DEP003,DEP004,DEP005"
REMOVED = re.compile(r"^-\s*(?:require\s+)?([^\s()]+)\s+(v\d\S*)(.*)$")  # a go.mod line `go mod tidy` would drop


class Unavailable(Exception):
    """The tool for a project isn't there: what it is, why, and the command that installs it ("" when none does)."""

    def __init__(self, tool: str, reason: str, install: str = "") -> None:
        super().__init__(reason)
        self.tool, self.reason, self.install = tool, reason, install


class Failed(Exception):
    """The tool ran and gave no answer; the message is its first error line."""


def rel(repo: Path, path: Path) -> str:
    """`path` relative to the repo as a POSIX path, `.` for the repo itself."""
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return str(path)


def new_row() -> dict:
    """The lists of one project's row: its unused packages, and its unused development packages (knip tells them)."""
    return {"unused": [], "dev": []}


def first_line(out: str, err: str) -> str:
    """The first line a failed tool wrote, from its stderr, else its stdout."""
    for text in (err, out):
        for row in text.splitlines():
            if row.strip():
                return row.strip()[:FIRST_LINE_CHARS]
    return "no output"


def execute(cmd: List[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    """Run `cmd` in `cwd`; its exit code and output, or Failed when it timed out or couldn't start."""
    rc, out, err = run(cmd, cwd, timeout=RUN_SECONDS, env=env)
    if rc is None:
        raise Failed(f"timed out after {RUN_SECONDS} s")
    if rc < 0:
        raise Failed(f"couldn't start {cmd[0]}")
    return rc, out, err


def decode(text: str, out: str, err: str) -> object:
    """The JSON in `text`; Failed with the tool's first error line when it isn't JSON."""
    try:
        return json.loads(text) if text.strip() else {}
    except ValueError:
        raise Failed(first_line(out, err))


def finish(rows: Dict[str, dict]) -> List[dict]:
    """The rows by project as a list, each list sorted and without repeats."""
    return [{"project": project, **{k: sorted(set(v)) for k, v in row.items()}} for project, row in rows.items()]


def names(items: object) -> List[str]:
    """The `name` of each item of a list of objects."""
    return [i["name"] for i in items if isinstance(i, dict) and i.get("name")] if isinstance(items, list) else []


# ---------------------------------------------------------------- the tools


def knip_rows(repo: Path, project: Path, data: object) -> List[dict]:
    """knip's JSON: one entry per file with issues, here the package.json of the project or of a workspace in it."""
    rows = {rel(repo, project): new_row()}
    for entry in (data.get("issues") if isinstance(data, dict) else None) or []:
        if isinstance(entry, dict) and Path(str(entry.get("file", ""))).name == "package.json":
            row = rows.setdefault(rel(repo, (project / str(entry["file"])).parent), new_row())
            row["unused"] += names(entry.get("dependencies"))
            row["dev"] += names(entry.get("devDependencies"))
    return finish(rows)


def knip(repo: Path, project: Path) -> List[dict]:
    """knip's unused dependencies and devDependencies in `project`, not its unused files and exports."""
    exe = resolve_bin("knip", project, repo)
    if not exe:
        raise Unavailable("knip", "knip is not installed", install_command(tools_db()["knip"]))
    rc, out, err = execute([exe, "--include", "dependencies", "--reporter", "json", "--no-progress"], project)
    if rc not in OK_CODES:  # 2: bad input, a plugin config that wouldn't load, or an internal error
        raise Failed(first_line(out, err))
    return knip_rows(repo, project, decode(out, out, err))


def deptry_rows(repo: Path, project: Path, data: object) -> List[dict]:
    """deptry's JSON, a list of violations: the modules of the DEP002 ones are the unused dependencies."""
    found = [v for v in data if isinstance(v, dict)] if isinstance(data, list) else []
    unused = [v.get("module", "") for v in found if (v.get("error") or {}).get("code") == "DEP002"]
    return finish({rel(repo, project): {"unused": unused, "dev": []}})


def deptry_exe(repo: Path, project: Path) -> Optional[str]:
    """The project's own deptry (its virtualenv's, which has the metadata of its packages) before the one on PATH."""
    for d in (project, repo):
        if (d / ".venv/bin/deptry").is_file():
            return str(d / ".venv/bin/deptry")
    return shutil.which("deptry")


def deptry(repo: Path, project: Path) -> List[dict]:
    """The dependencies `project` declares in pyproject.toml or requirements.txt and no code imports."""
    exe = deptry_exe(repo, project)
    if not exe:
        raise Unavailable("deptry", "deptry is not installed", install_command(tools_db()["deptry"]))
    with tempfile.TemporaryDirectory(prefix="broom-deptry-") as tmp:
        report = Path(tmp) / "deptry.json"
        cmd = [exe, ".", "--json-output", str(report), "--no-ansi", "--ignore", DEPTRY_OTHERS]
        rc, out, err = execute(cmd, project)
        if rc not in OK_CODES or not report.is_file():  # exit 1 is "violations", and an error exits 1 too
            raise Failed(first_line(out, err))
        text = report.read_text()
    return deptry_rows(repo, project, decode(text, out, err))


def machete_rows(repo: Path, project: Path, data: object) -> List[dict]:
    """cargo-machete's JSON: `{"crates": [{"package_name", "manifest_path", "unused": [...]}]}`, or `{}` for none."""
    rows = {rel(repo, project): new_row()}
    for crate in (data.get("crates") if isinstance(data, dict) else None) or []:
        if isinstance(crate, dict) and crate.get("manifest_path"):
            row = rows.setdefault(rel(repo, (project / str(crate["manifest_path"])).parent), new_row())
            row["unused"] += [str(n) for n in crate.get("unused") or []]
    return finish(rows)


def cargo_machete(repo: Path, project: Path) -> List[dict]:
    """The crates every Cargo.toml under `project` declares and nothing uses."""
    cargo = shutil.which("cargo")
    if not cargo or not shutil.which("cargo-machete"):
        raise Unavailable("cargo-machete", "cargo-machete is not installed",
                          install_command(tools_db()["cargo-machete"]))
    rc, out, err = execute([cargo, "machete", "--json", "."], project)
    if rc not in OK_CODES:  # 2: an error while it worked, so the result is unknown
        raise Failed(first_line(out, err))
    return machete_rows(repo, project, decode(out, out, err))


def tidy_rows(repo: Path, project: Path, diff: str) -> List[dict]:
    """The modules `go mod tidy -diff` would drop from go.mod: the removed requirements that aren't `// indirect`,
    which are only what the unused ones needed."""
    unused, in_mod = [], False
    for row in diff.splitlines():
        if row.startswith("diff "):
            in_mod = row.endswith("/go.mod")
        m = None if row.startswith("---") or not in_mod else REMOVED.match(row)
        if m and "// indirect" not in m[3]:
            unused.append(m[1])
    return finish({rel(repo, project): {"unused": unused, "dev": []}})


def go_version_error(repo: Path, go: str) -> str:
    """Why `go mod tidy -diff` can't be used with this Go ("" when it can, or when the version isn't read)."""
    rc, out, _ = run([go, "env", "GOVERSION"], repo, timeout=20)
    m = re.match(r"go(\d+)\.(\d+)", out.strip()) if rc == 0 else None
    if m and (int(m[1]), int(m[2])) < GO_TIDY_DIFF:
        return f"`go mod tidy -diff` needs Go 1.23 or later, and this is {out.strip()}"
    return ""


def go_tidy(repo: Path, project: Path) -> List[dict]:
    """The modules `project`'s go.mod requires and no package imports. With no network (GOPROXY=off): what the
    module cache lacks is an error, and `go mod download` fills it."""
    go = shutil.which("go")
    if not go:
        raise Unavailable("go mod tidy -diff", "go is not installed", install_command(tools_db()["go"]))
    why = go_version_error(repo, go)
    if why:
        raise Unavailable("go mod tidy -diff", why)
    rc, out, err = execute([go, "mod", "tidy", "-diff"], project, {"GOPROXY": "off"})
    if rc == 0 or "diff current/" in out:  # a diff is exit 1 too; an error writes `go: ...` to stderr
        return tidy_rows(repo, project, out)
    offline = " (broom uses no network: `go mod download` fetches what the module cache lacks)"
    raise Failed(first_line(out, err) + (offline if "GOPROXY=off" in err else ""))


# ---------------------------------------------------------------- the projects

TOOLS: Dict[str, Tuple[str, Callable[[Path, Path], List[dict]]]] = {
    "js": ("knip", knip), "py": ("deptry", deptry), "rust": ("cargo-machete", cargo_machete),
    "go": ("go mod tidy -diff", go_tidy),
}


def is_workspace_root(d: Path) -> bool:
    """Whether `d` holds a JS workspace: its package.json has `workspaces`, or it has a pnpm-workspace.yaml."""
    return "workspaces" in read_jsonc(d / "package.json") or (d / "pnpm-workspace.yaml").is_file()


def covering_dirs(lang: str, marked: List[Path]) -> List[Path]:
    """The directories whose tool run reads the ones below them: a JS workspace root, and any Rust directory."""
    if lang == "js":
        return [d for d in marked if is_workspace_root(d)]
    return marked if lang == "rust" else []


def project_dirs(lang: str, dirs: List[Path]) -> List[Path]:
    """The directories of `dirs` (a language's projects, from the doctor's scan) to run its tool in. Only those with
    one of its manifests. knip reads a whole workspace from its root, and cargo-machete every crate under a directory,
    so a directory under such a root is left to the run there."""
    marked = [d for d in dirs if any((d / m).is_file() for m in MARKERS[lang])]
    covering = covering_dirs(lang, marked)
    return [d for d in marked if not any(r != d and r in d.parents for r in covering)]


def overlaps(d: Path, paths: List[Path]) -> bool:
    """Whether a project directory and one of the paths a diagnosis was narrowed to hold one another; true with none."""
    return not paths or any(d == p or d in p.parents or p in d.parents for p in paths)


def failed_row(repo: Path, lang: str, tool: str, project: Path, error: str) -> dict:
    """The row of a project whose tool ran and gave no answer."""
    return {"ecosystem": lang, "tool": tool, "project": rel(repo, project), "status": "failed", "error": error,
            **new_row()}


def check(repo: Path, lang: str, dirs: List[Path]) -> Tuple[List[dict], List[dict]]:
    """The rows for a language's project directories, and, once, the tool that wasn't there."""
    tool, runner = TOOLS[lang]
    rows: List[dict] = []
    missing: Dict[str, dict] = {}
    for project in dirs:
        try:
            rows += [{"ecosystem": lang, "tool": tool, "status": "ok", "error": "", **row}
                     for row in runner(repo, project)]
        except Unavailable as e:
            missing[e.reason] = {"ecosystem": lang, "tool": e.tool, "reason": e.reason, "install": e.install}
        except Failed as e:
            rows.append(failed_row(repo, lang, tool, project, str(e)))
    return rows, list(missing.values())


def section(repo: Path, projects: Dict[str, List[Path]], paths: List[Path]) -> dict:
    """The diagnosis's Dependencies data: per ecosystem and project directory the unused packages by name (`projects`),
    and the tools that weren't there (`not_measured`). A diagnosis narrowed to `paths` takes the projects that
    overlap them."""
    rows: List[dict] = []
    missing: List[dict] = []
    skip = glob_matcher(repo_config(repo).get("exclude"))  # the repo's own paths to leave out of everything
    for lang in TOOLS:
        dirs = [d for d in project_dirs(lang, projects.get(lang, [])) if overlaps(d, paths)
                and not skip(rel(repo, d / MARKERS[lang][0]))]
        found, absent = check(repo, lang, dirs)
        rows += found
        missing += absent
    return {"projects": rows, "not_measured": missing}


# ---------------------------------------------------------------- the report


def cell(row: dict) -> str:
    """What a project row says in the table: its unused packages by name, its unused dev ones after them, or why not."""
    if row["status"] == "failed":
        return f"{row['tool']} failed: {row['error']}"
    parts = [", ".join(row["unused"])] if row["unused"] else []
    parts += [f"dev: {', '.join(row['dev'])}"] if row["dev"] else []
    return "; ".join(parts) or "none"


def lines(data: dict) -> List[str]:
    """The Dependencies section as text: a table of the projects, then each tool that wasn't there."""
    from .statsview import table  # not at the top: the session hook imports this module through the doctor

    rows = [[LANG_NAMES[r["ecosystem"]], r["project"], r["tool"], cell(r)] for r in data["projects"]]
    out = table(["language", "project", "tool", "unused packages"], rows, left=(0, 1, 2, 3))
    for m in data["not_measured"]:
        how = f" (`{m['install']}`)" if m["install"] else ""
        out.append(f"  not measured: {m['reason']}{how}")
    return out


# ---------------------------------------------------------------- the doctor's optional tools


def optional_tools(repo: Path, projects: Dict[str, List[Path]]) -> List[dict]:
    """The tools defaults/tools.json marks `optional` for the languages found, each with what it finds, whether it is
    installed and the command that installs it. They are looked up by name only, never run: the session start reads
    this through the doctor, and it is no gap, no fix and no part of the repo's health."""
    rows = []
    for name, spec in tools_db().items():
        lang = spec.get("lang", "any") if isinstance(spec, dict) and spec.get("optional") else None
        if lang and (projects if lang == "any" else lang in projects):
            here = any(resolve_bin(name, d, repo) for d in projects.get(lang, []))
            rows.append({"tool": name, "for": spec["for"], "installed": bool(shutil.which(name)) or here,
                         "install": install_command(spec)})
    return rows


def optional_lines(rows: List[dict]) -> List[str]:
    """The doctor's part for the optional tools: nothing for none; each with its mark, and the install command of one
    that is missing."""
    if not rows:
        return []
    width = max(len(r["tool"]) for r in rows)
    out = ["", "Optional, for `broom diagnose` (none of them is a gap, and none is installed for you):"]
    return out + [f"  {'✓' if r['installed'] else '○'} {r['tool'].ljust(width)}  {r['for']}"
                  + ("" if r["installed"] else f"  install: {r['install']}") for r in rows]
