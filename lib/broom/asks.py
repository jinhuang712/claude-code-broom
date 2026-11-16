"""The commands that answer a question: `fixes`, `report` and `stats`. `cli` imports this module, so each command's
own modules load only when that command runs."""

import argparse
import json
from pathlib import Path


def cmd_fixes(args: argparse.Namespace) -> int:
    """Print the usual fix of each smell named (all without names), as JSON with `--json`; exit 1 on an unknown name."""
    from .fixes import answer

    print(answer(args.names, as_json=args.json))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Print the `broom report` for the repos the paths are in (this repo without paths, every repo with `--all`) over
    `--days`, as JSON with `--json`. Returns 0, or exits with an error outside a git repo unless `--all` is given."""
    from .cli import repo_or_exit
    from .report import render, report

    roots = [] if args.all else [Path(p).resolve() for p in args.paths] or [repo_or_exit()]
    data = report(roots, args.days)
    print(json.dumps(data, indent=1) if args.json else render(data))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Print `broom stats` for the repo, narrowed to the paths given."""
    from .cli import repo_or_exit
    from .statsview import run

    return run(repo_or_exit(), args)


def add_ask_parsers(sub: argparse._SubParsersAction) -> None:
    """Register the commands that answer a question: `fixes`, `report` and `stats`, in that order."""
    fx = sub.add_parser("fixes", help="the usual fix of each kind of code smell, the lines the blocks carry")
    fx.add_argument("names", nargs="*", metavar="smell", help="only these smells (default: all)")
    fx.add_argument("--json", action="store_true", help="the same as JSON")
    fx.set_defaults(fn=cmd_fixes)
    r = sub.add_parser("report", help="what broom stopped, what was fixed and what went through, over a period")
    r.add_argument("paths", nargs="*", help="limit to these files or directories (default: the repo)")
    r.add_argument("--days", type=int, default=30, help="how far back to look (default: 30)")
    r.add_argument("--all", action="store_true", help="every repo, not only this one")
    r.add_argument("--json", action="store_true", help="the same as JSON")
    r.set_defaults(fn=cmd_report)
    s = sub.add_parser("stats", help="size, tests, rot and history of the repo or some paths, as counts")
    s.add_argument("paths", nargs="*", help="limit to these files or directories (default: the repo)")
    s.add_argument("--top", type=int, default=10, help="how long each list is (default: 10)")
    s.add_argument("--days", type=int, default=90, help="how far back history looks (default: 90)")
    s.add_argument("--json", action="store_true", help="the same as JSON")
    s.set_defaults(fn=cmd_stats)
