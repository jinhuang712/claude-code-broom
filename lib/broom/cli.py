"""`broom` command line: sweep, fmt, doctor, init, setup and known for people and skills; `hook` and `lsp` for
Claude Code."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import List, Optional, Tuple

from . import __version__
from .asks import add_ask_parsers
from .checks import run_checks
from .config import SETTINGS, SMELL_LIMITS, SMELL_PRESENCE, excluded, setting, setting_source
from .fmt import format_files
from .gate import (
    accept_allowed, accept_blocked, baseline_keys, baseline_remove, baseline_under, display, issue_key, render, select,
)
from .gitcmd import staged
from .hookmain import EVENTS, run_hook
from .gitutil import changed_since, ChangedLines, git, git_changed_files, git_root
from .scaffold import add_default_configs
from .smells import find_smells
from .state import say, warn
from .toolchain import lang_of


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
        found = changed_since(root, args.base)
        if found is None:
            raise SystemExit(f"broom: unknown revision {args.base!r}")
        files = found
        changed = ChangedLines(base=args.base)
    elif args.staged:
        files = sorted(staged(root))
        changed = ChangedLines(cached=True)
    else:
        files = git_changed_files(root)
    files = [f for f in dict.fromkeys(files) if f.is_file() and not excluded(f)]
    if args.paths:
        wanted = [Path(a).resolve() for a in args.paths]
        explicit = [p for p in wanted if p.is_file() and p not in files]
        files = [f for f in files if any(f == w or w in f.parents for w in wanted)] + explicit
    return files, changed, root


def sweep_smells(root: Path, code: List[Path], args: argparse.Namespace) -> int:
    """Print the code smells in scope: all of them with --all, else those the changes made worse."""
    if setting("smells", root) == "off":
        return 0
    found, notes = find_smells(root, code, None if args.all else (args.base or "HEAD"))
    if found or notes:
        what = "in the repo" if args.all else "the changes made worse"
        say(render(f"\n[broom] {len(found)} code smell(s) {what}.", [s.issue() for s in found], notes, set()))
    return len(found)


def cmd_sweep(args: argparse.Namespace) -> int:
    """Run `broom sweep` on the scope given: format the changed files, then lint and type-check; 1 if issues remain."""
    files, changed, root = scope_files(args)
    if not files:
        say("broom: nothing to sweep in that scope")
        return 0
    # Formatting a whole repo makes a huge diff: that takes an explicit --fix, which then means every line.
    if not args.check and (args.fix or not args.all):
        scope = "file" if args.all else (args.scope or setting("format_scope", Path.cwd()))
        fallbacks: List[str] = []
        for p, tool in format_files(files, scope=scope, changed=changed, notes=fallbacks):
            say(f"formatted {display(p)} ({tool})")
        for n in fallbacks:
            say(f"note: {n}")
    code = [f for f in files if lang_of(f)]
    issues, notes = run_checks(code, whole=args.all)
    every = select(issues, set(code), set(), changed, whole=args.all)
    known = set() if args.include_known else baseline_keys()
    found = [i for i in every if issue_key(i) not in known]
    hidden = len(every) - len(found)
    scope = "in the repo" if args.all else "in the changed lines"
    if found or notes:
        say(render(f"[broom] {len(found)} issue(s) {scope}.", found, notes, set() if args.all else set(code)))
    else:
        say(f"broom: clean ({len(code)} file(s))")
    if hidden:
        say(f"\n{hidden} known issue(s) hidden: `broom known` lists them, `--include-known` shows them here")
    smells = sweep_smells(root, code, args) if root else 0
    return 1 if found or smells else 0


def cmd_fmt(args: argparse.Namespace) -> int:
    """Run `broom fmt` on the changed files, or on the paths given, skipping excluded ones; always returns 0."""
    root = git_root(Path.cwd().resolve())
    files = git_changed_files(root) if root else []
    if args.paths:
        wanted = [Path(a).resolve() for a in args.paths]
        files = [f for f in files if any(f == w or w in f.parents for w in wanted)] + [w for w in wanted if w.is_file()]
    fallbacks: List[str] = []
    files = [f for f in dict.fromkeys(files) if not excluded(f)]
    changed = format_files(files, scope=args.scope or setting("format_scope", Path.cwd()), notes=fallbacks)
    for p, tool in changed:
        say(f"formatted {display(p)} ({tool})")
    for n in fallbacks:
        say(f"note: {n}")
    if not changed:
        say("broom: nothing to format")
    return 0


# ---------------------------------------------------------------- doctor, setup, init


def repo_or_exit() -> Path:
    """The git root of the current directory; exits with a message when it is not inside a repository."""
    root = git_root(Path.cwd().resolve())
    if root is None:
        raise SystemExit("broom: not inside a git repository")
    return root


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run `broom doctor`: the repo's tools and configs with their fixes, as JSON with --json; 1 when not healthy."""
    from .doctor import answered_kinds, diagnose, gap_kind, render_text

    repo = repo_or_exit()
    result = diagnose(repo)
    if args.json:
        known = answered_kinds()
        for i in result["items"]:  # answered in some repo already: setup doesn't raise it again
            i["answered"] = i["status"] != "ok" and gap_kind(i) in known
        result["settings"] = {name: dict(zip(("value", "source"), setting_source(name, repo))) for name in SETTINGS}
    say(json.dumps(result, indent=1) if args.json else render_text(result))
    return 0 if result["healthy"] else 1


def cmd_setup(args: argparse.Namespace) -> int:
    """Run `broom setup`: record the answer (done, dismissed or reset) and say how many gaps are left; returns 0."""
    from .doctor import gaps, record_setup, reset_setup

    if args.reset:
        say(f"broom: forgot {reset_setup()} setup answer(s); setup will ask about every gap again")
        return 0
    status = "dismissed" if args.dismiss else "done"
    result = record_setup(repo_or_exit(), status)
    left = len(gaps(result))
    say(f"broom: setup {status}" + (f"; {left} gap(s) left as they are, and broom won't ask about these kinds of "
                                     "gap again in any repo (`broom setup --reset` to undo)" if left else ""))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Add broom's default configs where the project has none. Never overwrites."""
    from .doctor import scan

    here = Path.cwd().resolve()
    root = Path(args.dir).resolve() if args.dir else (git_root(here) or here)
    # Configs are found by walking up: at a monorepo root they cover every package below.
    actions = add_default_configs(root, scan(root), dry_run=args.dry_run)
    say("\n".join(actions) if actions else f"broom: {display(root)} already has its configs")
    return 0


# ---------------------------------------------------------------- known issues


def cmd_smells(args: argparse.Namespace) -> int:
    """Run `broom smells`: the repo's code smells, worst first (JSON with --json), or dismiss them; returns 0."""
    from .hotspots import Ask, dismiss, render, report

    repo = repo_or_exit()
    if args.dismiss:
        say(dismiss(repo))
        return 0
    ask = Ask(args.top, args.base, args.by, tuple(args.only or ()))
    data = report(repo, [Path(p).resolve() for p in args.paths], ask)
    say(json.dumps(data, indent=1) if args.json else render(data))
    return 0


def cmd_known(args: argparse.Namespace) -> int:
    """Run `broom known`: list the known issues here, accept the last blocked ones with a reason, or clear them."""
    roots = [Path(p).resolve() for p in args.paths] or [repo_or_exit()]
    if args.accept is not None:
        if not accept_allowed():
            raise SystemExit("broom: accepting is off here (BROOM_NO_ACCEPT is set): fix the issues, or ask the user")
        why = args.accept.strip()
        if not why:
            raise SystemExit('broom: say why: broom known --accept "<why>"')
        repo = git_root(roots[0] if roots[0].is_dir() else roots[0].parent)
        if repo is None:
            raise SystemExit("broom: not inside a git repository")
        n, where = accept_blocked(repo, why)
        if not n:
            say(f"broom: no blocked commit or turn end to accept in {display(repo)}")
            return 1
        again = "stop again" if where.endswith("stop") else "commit again"
        say(f"broom: accepted {n} issue(s) as known ({why}); {again}")
        return 0
    entries = baseline_under(roots)
    if args.clear:
        baseline_remove(list(entries))
        say(f"broom: cleared {len(entries)} known issue(s)")
        return 0
    if not entries:
        say("broom: no known issues here")
        return 0
    say(f"broom: {len(entries)} known issue(s), not raised again:")
    for e in sorted(entries.values(), key=lambda v: (str(v.get("file")), v.get("line", 0))):
        when = time.strftime("%Y-%m-%d", time.localtime(e.get("t", 0)))
        where = f"{display(Path(str(e.get('file', '?'))))}:{e.get('line', '?')}"
        why = f"  ({e['why']})" if e.get("why") else ""
        msg = e.get("msg", "(recorded by broom 0.2)")
        say(f"  {where}  {e.get('tool', '?')} {e.get('rule', '')}  {msg}  [{when}]{why}")
    return 0


# ---------------------------------------------------------------- hooks


def cmd_install_hook(_args: argparse.Namespace) -> int:
    """Run `broom install-hook`: add broom's line to the repo's git hook; 1 when that hook belongs to another tool."""
    from .githook import LINE, install

    written, path = install(repo_or_exit())
    if not written:
        say(f"broom: {display(path)} is another tool's hook; add this line to it instead:\n  {LINE}")
        return 1
    say(f"broom: added {display(path)}: commits Claude Code's commit hook doesn't see are checked too")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Run `broom hook <event>`. bin/broom goes to hookmain itself, without loading this module."""
    return run_hook(args.event)


def cmd_lsp(_args: argparse.Namespace) -> int:
    """Become the language server this project needs. Claude Code starts it from the project directory, with
    stdin and stdout as the protocol channel, so the chosen server replaces this process."""
    from .lsp import typescript_server

    cmd, why = typescript_server(Path.cwd().resolve())
    if cmd is None:
        warn(f"broom: no TypeScript language server here: {why}. Run broom doctor.")
        return 1
    warn(f"broom: TypeScript language server: {why}")
    os.execvp(cmd[0], cmd)
    return 1  # not reached


SCOPE_HELP = "format changed lines, the functions holding them, or whole files (default: the format_scope setting)"


def add_sweep_parsers(sub: argparse._SubParsersAction) -> None:
    """Add the `sweep` subcommand and its scope and mode flags to the subparsers `sub`, with its handler."""
    s = sub.add_parser("sweep", help="format, then lint and type-check a scope (default: uncommitted changes)")
    scope = s.add_mutually_exclusive_group()
    scope.add_argument("--staged", action="store_true", help="only the staged changes")
    scope.add_argument("--base", metavar="REV", help="changes since REV, e.g. HEAD~3 or $(git merge-base HEAD main)")
    scope.add_argument("--all", action="store_true", help="the whole repo, every line (report only unless --fix)")
    mode = s.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report only, don't format")
    mode.add_argument("--fix", action="store_true", help="with --all, also format every file")
    s.add_argument("--include-known", action="store_true", help="also show issues accepted earlier")
    s.add_argument("--scope", choices=["changed", "function", "file"], help=SCOPE_HELP)
    s.add_argument("paths", nargs="*", help="narrow the scope to these files or directories")
    s.set_defaults(fn=cmd_sweep)
    f = sub.add_parser("fmt", help="format changed files (default: uncommitted changes)")
    f.add_argument("--scope", choices=["changed", "function", "file"], help=SCOPE_HELP)
    f.add_argument("paths", nargs="*")
    f.set_defaults(fn=cmd_fmt)


def add_setup_parsers(sub: argparse._SubParsersAction) -> None:
    """Add the `doctor` and `setup` subcommands and their flags to the subparsers `sub`, each with its handler."""
    d = sub.add_parser("doctor", help="languages, tools, configs and conflicts for this repo, with fixes")
    d.add_argument("--json", action="store_true")
    d.set_defaults(fn=cmd_doctor)
    st = sub.add_parser("setup", help="record that setup is done, or declined; the answer holds in every repo")
    st_mode = st.add_mutually_exclusive_group(required=True)
    st_mode.add_argument("--done", action="store_true")
    st_mode.add_argument("--dismiss", action="store_true")
    st_mode.add_argument("--reset", action="store_true", help="forget every answer, so setup asks again everywhere")
    st.set_defaults(fn=cmd_setup)
    i = sub.add_parser("init", help="add default lint/format configs where a project has none")
    i.add_argument("dir", nargs="?", help="project directory (default: the repo root)")
    i.add_argument("--dry-run", action="store_true")
    i.set_defaults(fn=cmd_init)


def add_issue_parsers(sub: argparse._SubParsersAction) -> None:
    """Add the `known` and `smells` subcommands and their flags to the subparsers `sub`, each with its handler."""
    k = sub.add_parser("known", help="list, --accept or --clear issues accepted as known")
    k.add_argument("--accept", metavar="WHY",
                   help="accept the issues of the last blocked commit or turn end here, with the reason")
    k.add_argument("--clear", action="store_true")
    k.add_argument("paths", nargs="*", help="limit to these files or directories (default: the repo)")
    k.set_defaults(fn=cmd_known)
    m = sub.add_parser("smells", help="the code smells in the repo or some paths, worst first, for a cleanup")
    m.add_argument("paths", nargs="*", help="limit to these files or directories (default: the repo)")
    m.add_argument("--base", metavar="REV", help="only what the changes since REV made worse, e.g. HEAD or main")
    m.add_argument("--top", type=int, default=10, help="how many hotspot files and smells to list (default: 10)")
    m.add_argument("--by", choices=["churn", "smells"], default="churn",
                   help="order the hotspots by smells times recent changes, or by smells alone (default: churn)")
    m.add_argument("--only", metavar="SMELL", action="append", choices=sorted([*SMELL_LIMITS, *SMELL_PRESENCE]),
                   help="only this kind of smell, e.g. function_lines for the longest functions; may repeat")
    m.add_argument("--json", action="store_true", help="the same as JSON")
    m.add_argument("--dismiss", action="store_true", help="quiet the session note until severe smells grow")
    m.set_defaults(fn=cmd_smells)
    ih = sub.add_parser("install-hook", help="add a git pre-commit hook for commits Claude Code's hook doesn't see")
    ih.set_defaults(fn=cmd_install_hook)


def add_internal_parsers(sub: argparse._SubParsersAction) -> None:
    """Commands for Claude Code and git, left out of --help."""
    h = sub.add_parser("hook")
    h.add_argument("event", choices=EVENTS)
    h.set_defaults(fn=cmd_hook)
    ls = sub.add_parser("lsp")  # for .lsp.json
    ls.add_argument("language", choices=["typescript"])
    ls.set_defaults(fn=cmd_lsp)


def main(argv: List[str]) -> int:
    """Parse `argv` with the broom subcommands, run the chosen one and return its exit code."""
    p = argparse.ArgumentParser(prog="broom", description="Format, lint and type-check with each project's own tools.")
    p.add_argument("--version", action="version", version=f"broom {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True,
                           metavar="{sweep,smells,fixes,fmt,doctor,setup,init,known,report,stats,diagnose,compare,install-hook}")
    for add in (add_sweep_parsers, add_setup_parsers, add_issue_parsers, add_ask_parsers, add_internal_parsers):
        add(sub)
    args = p.parse_args(argv)
    if args.cmd == "sweep" and args.fix and not args.all:
        args.fix = False  # formatting is the default outside --all
    return args.fn(args)
