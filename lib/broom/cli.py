"""`broom` command line: sweep, fmt and init for people and skills; `hook` for Claude Code."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import List

from . import __version__
from .checks import run_checks
from .common import (
    BIOME_CFG, DEFAULTS, ESLINT_CFG, GOLANGCI_CFG, OXFMT_CFG, OXLINT_CFG, PRETTIER_CFG, git_changed_files,
    git_root, lang_of, pkg_has_key, read_hook_input, ruff_configured, run,
)
from .fmt import format_files
from .gate import render, select
from .gitcmd import staged


def target_files(paths: List[str], staged_only: bool) -> List[Path]:
    """The given files, the changed files under given directories, or the repo's uncommitted changes."""
    cwd = Path.cwd().resolve()
    root = git_root(cwd)
    changed = (sorted(staged(root)) if staged_only else git_changed_files(root)) if root else []
    if not paths:
        return changed
    files: List[Path] = []
    for a in paths:
        p = Path(a).resolve()
        if p.is_dir():
            files += [f for f in changed if p in f.parents]
        elif p.is_file():
            files.append(p)
    return list(dict.fromkeys(files))


def cmd_sweep(args: argparse.Namespace) -> int:
    files = target_files(args.paths, args.staged)
    if not files:
        print("broom: no changed files")
        return 0
    if not args.check:
        for p, tool in format_files(files):
            print(f"formatted {p} ({tool})")
    code = [f for f in files if lang_of(f)]
    issues, notes = run_checks(code)
    found = select(issues, set(code), set())
    if found or notes:
        print(render(f"[broom] {len(found)} issue(s) in the changed lines.", found, notes, set(code)))
    else:
        print("broom: clean")
    return 1 if found else 0


def cmd_fmt(args: argparse.Namespace) -> int:
    changed = format_files(target_files(args.paths, False))
    for p, tool in changed:
        print(f"formatted {p} ({tool})")
    if not changed:
        print("broom: nothing to format")
    return 0


GOLANGCI_FORMATTERS = """
formatters:
  enable:
    - gofumpt
    - goimports
"""
RUFF_DEFAULT = """[lint]
select = ["E4", "E7", "E9", "F", "B", "UP"]
"""


def cmd_init(args: argparse.Namespace) -> int:
    """Add broom's default configs where the project has none. Never overwrites."""
    root = git_root(Path.cwd().resolve()) or Path.cwd().resolve()
    has = lambda names: any((root / n).exists() for n in names)  # noqa: E731
    actions: List[str] = []

    def write(name: str, text: str) -> None:
        actions.append(f"{'would add' if args.dry_run else 'added'} {name}")
        if not args.dry_run:
            (root / name).write_text(text)

    if (root / "go.mod").exists() and not has(GOLANGCI_CFG):
        write(".golangci.yml", (DEFAULTS / "golangci.yml").read_text() + GOLANGCI_FORMATTERS)
    if (root / "package.json").exists() or (root / "tsconfig.json").exists():
        if not has(OXLINT_CFG) and not has(ESLINT_CFG) and not has(BIOME_CFG):
            write(".oxlintrc.json", (DEFAULTS / "oxlintrc.json").read_text())
        if not has(BIOME_CFG) and not has(OXFMT_CFG) and not has(PRETTIER_CFG) and not pkg_has_key(root, "prettier"):
            oxfmt = shutil.which("oxfmt")
            if oxfmt and not args.dry_run:
                run([oxfmt, "--init"], root, timeout=30)
                actions.append("added .oxfmtrc.json (oxfmt --init)")
            else:
                write(".oxfmtrc.json", "{}\n")
    if any((root / n).exists() for n in ("pyproject.toml", "setup.py", "requirements.txt")) \
            and not ruff_configured(root / "x.py", root):
        if (root / "pyproject.toml").exists():
            actions.append("pyproject.toml has no ruff settings; add this under [tool.ruff.lint]:\n"
                           + RUFF_DEFAULT.split("\n", 1)[1])
        else:
            write("ruff.toml", RUFF_DEFAULT)
    print("\n".join(actions) if actions else "broom: every language here already has its configs")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    from .hooks import hook_commit, hook_edit, hook_stop

    data = read_hook_input()
    try:
        {"commit": hook_commit, "edit": hook_edit, "stop": hook_stop}[args.event](data)
    except Exception as e:  # a broken check must never trap Claude or block its edits
        print(f"broom hook {args.event}: {e}", file=sys.stderr)
    return 0


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(prog="broom", description="Format and lint what changed, with each project's own tools.")
    p.add_argument("--version", action="version", version=f"broom {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{sweep,fmt,init}")
    s = sub.add_parser("sweep", help="format, then lint and type-check changed files (default: uncommitted changes)")
    s.add_argument("--check", action="store_true", help="report only, don't format")
    s.add_argument("--staged", action="store_true", help="only the staged files")
    s.add_argument("paths", nargs="*")
    s.set_defaults(fn=cmd_sweep)
    f = sub.add_parser("fmt", help="format changed files (default: uncommitted changes)")
    f.add_argument("paths", nargs="*")
    f.set_defaults(fn=cmd_fmt)
    i = sub.add_parser("init", help="add default lint/format configs where the project has none")
    i.add_argument("--dry-run", action="store_true")
    i.set_defaults(fn=cmd_init)
    h = sub.add_parser("hook")  # for Claude Code; left out of --help
    h.add_argument("event", choices=["commit", "edit", "stop"])
    h.set_defaults(fn=cmd_hook)
    args = p.parse_args(argv)
    return args.fn(args)
