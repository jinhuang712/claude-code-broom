"""The dependency-cruiser broom runs for cycles between folders in TS/JS. It reads a .ts file only with a TypeScript
below 7 beside it, and says nothing when it has none, so broom keeps a copy of its own under its data directory, with
a TypeScript 6 beside it: it reads the project's code whatever TypeScript the project uses, and touches nothing of the
user's. A dependency-cruiser of the project or of PATH is used only where the TypeScript beside it lets it read. The
same copy holds a typescript-language-server, which has no TypeScript of its own and loads the one beside it."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from .gitutil import git
from .state import DATA_ROOT
from .toolchain import resolve_bin

OWN_DIR = DATA_ROOT / "node"  # where broom's own copy is installed, with `npm i --prefix`
OWN_PACKAGES = "dependency-cruiser typescript-language-server typescript@6"
TS_EXTS = (".ts", ".tsx", ".mts", ".cts")
TS_LIMIT = 7  # dependency-cruiser reads .ts files only with a TypeScript below this major version
READS_NO_TS = "dependency-cruiser reads no .ts file"  # how the reason a copy doesn't count begins


def install_command() -> str:
    """The command that installs broom's own copy: the same whether or not the user keeps JS tools global."""
    return f'npm i --prefix "{OWN_DIR}" {OWN_PACKAGES}'


def own_copy() -> Optional[str]:
    """The `depcruise` of broom's own copy, None when it isn't installed."""
    exe = OWN_DIR / "node_modules" / ".bin" / "depcruise"
    return str(exe) if exe.is_file() else None


def own_server() -> Optional[str]:
    """The `typescript-language-server` of broom's own copy, None when it isn't installed."""
    exe = OWN_DIR / "node_modules" / ".bin" / "typescript-language-server"
    return str(exe) if exe.is_file() else None


def typescript_beside(exe: str) -> Optional[str]:
    """The version of the `typescript` package that Node would load from the folder of `exe` (dependency-cruiser or
    typescript-language-server), read with no process started: from the real path of `exe` up through each enclosing
    node_modules (the package's own first, then the one that holds it, then those of its ancestors). None when there
    is none."""
    for folder in Path(os.path.realpath(exe)).parents:
        if folder.name == "node_modules":  # Node looks for node_modules/node_modules in none
            continue
        try:
            version = json.loads((folder / "node_modules" / "typescript" / "package.json").read_text())["version"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(version, str):
            return version
    return None


def holds_typescript(repo: Path) -> bool:
    """Whether the repo has a .ts, .tsx, .mts or .cts file, tracked or not yet but not ignored."""
    return bool(git(["ls-files", "--cached", "--others", "--exclude-standard", "--", *[f"*{e}" for e in TS_EXTS]], repo))


def blind_why(repo: Path, exe: str) -> str:
    """Why the dependency-cruiser `exe` reads no .ts file in `repo`: the TypeScript beside it is 7 or later, or there is
    none. Empty when it reads them, when the repo has no TypeScript, or when `exe` isn't one installed with npm (a
    script outside any node_modules says nothing about what sits beside it)."""
    if "node_modules" not in Path(os.path.realpath(exe)).parts or not holds_typescript(repo):
        return ""
    version = typescript_beside(exe)
    if version is None:
        return f"{READS_NO_TS}: there is no TypeScript beside it, and it needs one below {TS_LIMIT}"
    major = re.match(r"\d+", version)
    if major and int(major.group()) >= TS_LIMIT:
        return f"{READS_NO_TS}: the TypeScript beside it is {version}, and it needs one below {TS_LIMIT}"
    return ""


def choose(repo: Path, own: Optional[str] = None) -> Tuple[Optional[str], str]:
    """The dependency-cruiser to run for `repo`, and why not when only one that is blind for it is installed: broom's
    own copy (`own`, found when not given), else the project's or the PATH's unless the TypeScript beside it stops it."""
    own = own or own_copy()
    if own:
        return own, ""
    found = resolve_bin("depcruise", repo, repo)
    why = blind_why(repo, found) if found else ""
    return (None, why) if why else (found, "")


def pick(repo: Path) -> Optional[str]:
    """The dependency-cruiser to run for `repo`, None when there is none that reads its code."""
    return choose(repo)[0]
