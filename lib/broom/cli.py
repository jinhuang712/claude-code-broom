"""`broom` command line: sweep, fmt, doctor, init, setup and known for people and skills; `hook` for Claude Code."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from . import __version__
from .checks import run_checks
from .common import (
    BIOME_CFG, DEFAULTS, ESLINT_CFG, GOLANGCI_CFG, OXFMT_CFG, OXLINT_CFG, PRETTIER_CFG, ChangedLines, git,
    git_changed_files, git_root, lang_of, pkg_has_key, read_hook_input, ruff_configured, run, setting,
)
from .fmt import format_files
from .gate import baseline_keys, baseline_remove, baseline_under, display, issue_key, render, select
from .gitcmd import staged


# ---------------------------------------------------------------- sweep and fmt


def scope_files(args: argparse.Namespace) -> Tuple[List[Path], ChangedLines, Optional[Path]]:
    """The files a sweep covers, how their changed lines are measured, and the repo."""
    root = git_root(Path.cwd().resolve())
    changed = ChangedLines()
    if root is None:
        files: List[Path] = []
    elif args.all:
        out = git(["ls-files", "--cached", "--others", "--exclude-standard"], root) or ""
        files = [(root / n).resolve() for n in out.splitlines() if n]
    elif args.base:
        out = git(["diff", "--name-only", "--diff-filter=ACMR", args.base], root)
        if out is None:
            raise SystemExit(f"broom: unknown revision {args.base!r}")
        untracked = git(["ls-files", "--others", "--exclude-standard"], root) or ""
        files = [(root / n).resolve() for n in (out + untracked).splitlines() if n]
        changed = ChangedLines(base=args.base)
    elif args.staged:
        files = sorted(staged(root))
        changed = ChangedLines(cached=True)
    else:
        files = git_changed_files(root)
    files = [f for f in dict.fromkeys(files) if f.is_file()]
    if args.paths:
        wanted = [Path(a).resolve() for a in args.paths]
        explicit = [p for p in wanted if p.is_file() and p not in files]
        files = [f for f in files if any(f == w or w in f.parents for w in wanted)] + explicit
    return files, changed, root


def cmd_sweep(args: argparse.Namespace) -> int:
    files, changed, _ = scope_files(args)
    if not files:
        print("broom: nothing to sweep in that scope")
        return 0
    # Formatting a whole repo makes a huge diff: that takes an explicit --fix, which then means every line.
    if not args.check and (args.fix or not args.all):
        scope = "file" if args.all else (args.scope or setting("format_scope"))
        for p, tool in format_files(files, scope=scope, changed=changed):
            print(f"formatted {display(p)} ({tool})")
    code = [f for f in files if lang_of(f)]
    issues, notes = run_checks(code, whole=args.all)
    every = select(issues, set(code), set(), changed, whole=args.all)
    known = set() if args.include_known else baseline_keys()
    found = [i for i in every if issue_key(i) not in known]
    hidden = len(every) - len(found)
    scope = "in the repo" if args.all else "in the changed lines"
    if found or notes:
        print(render(f"[broom] {len(found)} issue(s) {scope}.", found, notes, set() if args.all else set(code)))
    else:
        print(f"broom: clean ({len(code)} file(s))")
    if hidden:
        print(f"\n{hidden} known issue(s) hidden: `broom known` lists them, `--include-known` shows them here")
    return 1 if found else 0


def cmd_fmt(args: argparse.Namespace) -> int:
    root = git_root(Path.cwd().resolve())
    files = git_changed_files(root) if root else []
    if args.paths:
        wanted = [Path(a).resolve() for a in args.paths]
        files = [f for f in files if any(f == w or w in f.parents for w in wanted)] + [w for w in wanted if w.is_file()]
    changed = format_files(list(dict.fromkeys(files)), scope=args.scope or setting("format_scope"))
    for p, tool in changed:
        print(f"formatted {display(p)} ({tool})")
    if not changed:
        print("broom: nothing to format")
    return 0


# ---------------------------------------------------------------- doctor, setup, init


def repo_or_exit() -> Path:
    root = git_root(Path.cwd().resolve())
    if root is None:
        raise SystemExit("broom: not inside a git repository")
    return root


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import diagnose, render_text

    result = diagnose(repo_or_exit())
    print(json.dumps(result, indent=1) if args.json else render_text(result))
    return 0 if result["healthy"] else 1


def cmd_setup(args: argparse.Namespace) -> int:
    from .doctor import gaps, record_setup

    status = "dismissed" if args.dismiss else "done"
    result = record_setup(repo_or_exit(), status)
    left = len(gaps(result))
    print(f"broom: setup {status}" + (f"; {left} gap(s) left as they are, broom won't ask again until that changes"
                                       if left else ""))
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
    root = Path(args.dir).resolve() if args.dir else (git_root(Path.cwd().resolve()) or Path.cwd().resolve())
    has = lambda names: any((root / n).exists() for n in names)  # noqa: E731
    actions: List[str] = []

    def write(name: str, text: str) -> None:
        actions.append(f"{'would add' if args.dry_run else 'added'} {name}")
        if not args.dry_run:
            (root / name).write_text(text)

    from .doctor import scan

    langs = scan(root)  # configs are found by walking up: at a monorepo root they cover every package below
    if "go" in langs and not has(GOLANGCI_CFG):
        write(".golangci.yml", (DEFAULTS / "golangci.yml").read_text() + GOLANGCI_FORMATTERS)
    if "js" in langs:
        if not has(OXLINT_CFG) and not has(ESLINT_CFG) and not has(BIOME_CFG):
            write(".oxlintrc.json", (DEFAULTS / "oxlintrc.json").read_text())
        if not has(BIOME_CFG) and not has(OXFMT_CFG) and not has(PRETTIER_CFG) and not pkg_has_key(root, "prettier"):
            oxfmt = shutil.which("oxfmt")
            if oxfmt and not args.dry_run:
                run([oxfmt, "--init"], root, timeout=30)
            if not (root / ".oxfmtrc.json").exists():
                write(".oxfmtrc.json", "{}\n")
            elif not args.dry_run:
                actions.append("added .oxfmtrc.json (oxfmt --init)")
    if "py" in langs and not ruff_configured(root / "_.py", root):
        if (root / "pyproject.toml").exists():
            actions.append("pyproject.toml has no ruff settings; add this under [tool.ruff.lint]:\n"
                           + RUFF_DEFAULT.split("\n", 1)[1])
        else:
            write("ruff.toml", RUFF_DEFAULT)
    print("\n".join(actions) if actions else f"broom: {display(root)} already has its configs")
    return 0


# ---------------------------------------------------------------- known issues


def cmd_known(args: argparse.Namespace) -> int:
    roots = [Path(p).resolve() for p in args.paths] or [repo_or_exit()]
    entries = baseline_under(roots)
    if args.clear:
        baseline_remove(list(entries))
        print(f"broom: cleared {len(entries)} known issue(s)")
        return 0
    if not entries:
        print("broom: no known issues here")
        return 0
    print(f"broom: {len(entries)} known issue(s), accepted after Claude saw them and committed or stopped again:")
    for e in sorted(entries.values(), key=lambda v: (str(v.get("file")), v.get("line", 0))):
        when = time.strftime("%Y-%m-%d", time.localtime(e.get("t", 0)))
        where = f"{display(Path(str(e.get('file', '?'))))}:{e.get('line', '?')}"
        print(f"  {where}  {e.get('tool', '?')} {e.get('rule', '')}  {e.get('msg', '(recorded by broom 0.2)')}  [{when}]")
    return 0


# ---------------------------------------------------------------- hooks


def cmd_hook(args: argparse.Namespace) -> int:
    from .hooks import hook_commit, hook_edit, hook_session, hook_stop

    data = read_hook_input()
    try:
        {"commit": hook_commit, "edit": hook_edit, "stop": hook_stop, "session": hook_session}[args.event](data)
    except Exception as e:  # a broken check must never trap Claude or block its edits
        print(f"broom hook {args.event}: {e}", file=sys.stderr)
    return 0


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(prog="broom", description="Format, lint and type-check with each project's own tools.")
    p.add_argument("--version", action="version", version=f"broom {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{sweep,fmt,doctor,setup,init,known}")

    s = sub.add_parser("sweep", help="format, then lint and type-check a scope (default: uncommitted changes)")
    scope = s.add_mutually_exclusive_group()
    scope.add_argument("--staged", action="store_true", help="only the staged changes")
    scope.add_argument("--base", metavar="REV", help="changes since REV, e.g. HEAD~3 or $(git merge-base HEAD main)")
    scope.add_argument("--all", action="store_true", help="the whole repo, every line (report only unless --fix)")
    mode = s.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report only, don't format")
    mode.add_argument("--fix", action="store_true", help="with --all, also format every file")
    s.add_argument("--include-known", action="store_true", help="also show issues accepted earlier")
    s.add_argument("--scope", choices=["changed", "file"], help="format only changed lines, or whole files "
                   "(default: the format_scope setting)")
    s.add_argument("paths", nargs="*", help="narrow the scope to these files or directories")
    s.set_defaults(fn=cmd_sweep)

    f = sub.add_parser("fmt", help="format changed files (default: uncommitted changes)")
    f.add_argument("--scope", choices=["changed", "file"], help="format only changed lines, or whole files "
                   "(default: the format_scope setting)")
    f.add_argument("paths", nargs="*")
    f.set_defaults(fn=cmd_fmt)

    d = sub.add_parser("doctor", help="languages, tools, configs and conflicts for this repo, with fixes")
    d.add_argument("--json", action="store_true")
    d.set_defaults(fn=cmd_doctor)

    st = sub.add_parser("setup", help="record that setup is done, or declined, for this repo")
    st_mode = st.add_mutually_exclusive_group(required=True)
    st_mode.add_argument("--done", action="store_true")
    st_mode.add_argument("--dismiss", action="store_true")
    st.set_defaults(fn=cmd_setup)

    i = sub.add_parser("init", help="add default lint/format configs where a project has none")
    i.add_argument("dir", nargs="?", help="project directory (default: the repo root)")
    i.add_argument("--dry-run", action="store_true")
    i.set_defaults(fn=cmd_init)

    k = sub.add_parser("known", help="list (or --clear) issues accepted as known")
    k.add_argument("--clear", action="store_true")
    k.add_argument("paths", nargs="*", help="limit to these files or directories (default: the repo)")
    k.set_defaults(fn=cmd_known)

    h = sub.add_parser("hook")  # for Claude Code; left out of --help
    h.add_argument("event", choices=["commit", "edit", "stop", "session"])
    h.set_defaults(fn=cmd_hook)

    args = p.parse_args(argv)
    if args.cmd == "sweep" and args.fix and not args.all:
        args.fix = False  # formatting is the default outside --all
    return args.fn(args)
