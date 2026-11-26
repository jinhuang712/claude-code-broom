"""The commands that answer a question: `fixes`, `report`, `stats`, `diagnose` and `compare`. `cli` imports this
module, so each command's own modules load only when that command runs."""

import argparse
import json
import sys
from pathlib import Path

from .statsgit import CHURN_COMMITS


def cmd_fixes(args: argparse.Namespace) -> int:
    """Print the usual fix of each smell named (all without names), as JSON with `--json`; exit 1 on an unknown name."""
    from .fixes import answer

    sys.stdout.write(answer(args.names, as_json=args.json) + "\n")
    return 0


def broom_version(text: str) -> str:
    """A broom version such as `0.28.5`, for `--since`; argparse says (and exits 2) when the text is none."""
    from .report import version_key

    if version_key(text) is None:
        raise argparse.ArgumentTypeError(f"not a version such as 0.28.5: {text!r}")
    return text


def cmd_report(args: argparse.Namespace) -> int:
    """Print the `broom report` for the repos the paths are in (this repo without paths, every repo with `--all`) over
    `--since`, as JSON with `--json`. Returns 0, or exits with an error outside a git repo unless `--all` is given."""
    from .cli import repo_or_exit
    from .report import render, report

    roots = [] if args.all else [Path(p).resolve() for p in args.paths] or [repo_or_exit()]
    data = report(roots, args.since)
    sys.stdout.write((json.dumps(data, indent=1) if args.json else render(data)) + "\n")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Print `broom stats` for the repo, narrowed to the paths given."""
    from .cli import repo_or_exit
    from .statsview import run

    return run(repo_or_exit(), args)


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Print the diagnosis of the whole repo, narrowed to the paths given, or write it to `--out`; exit 1 outside a
    git repository."""
    from .cli import repo_or_exit
    from .diagnoseview import run

    return run(repo_or_exit(), args)


def cmd_compare(args: argparse.Namespace) -> int:
    """Print what the work since a revision did to the repo's smells; exit 1 for an unknown revision or outside a git
    repository."""
    from .cli import repo_or_exit
    from .compareview import run

    return run(repo_or_exit(), args)


def add_diagnosis_parsers(sub: argparse._SubParsersAction) -> None:
    """Register `diagnose` and `compare`."""
    d = sub.add_parser("diagnose", help="the whole repo measured: smells, hotspots by churn and stats, as a report")
    d.add_argument("paths", nargs="*", help="limit to these files or directories (default: the repo)")
    d.add_argument("--top", type=int, default=10, help="how long each list is (default: 10)")
    d.add_argument("--commits", type=int, default=CHURN_COMMITS,
                   help=f"how many of the last commits changes are counted over (default: {CHURN_COMMITS})")
    d.add_argument("--json", action="store_true", help="the same as JSON, with every smell")
    d.add_argument("--out", metavar="FILE", help="write the report (or the JSON) to FILE and say where")
    d.add_argument("--vulnerabilities", action="store_true",
                   help="also look up known vulnerabilities with osv-scanner, which sends package names and versions "
                        "to osv.dev")
    d.set_defaults(fn=cmd_diagnose)
    c = sub.add_parser("compare", help="what the work since a revision did to the smells: gone, new, smaller, bigger")
    c.add_argument("base", metavar="BASE", help="the revision to compare with, e.g. v1.2.0 or main~20")
    c.add_argument("--top", type=int, default=10, help="how many hotspots, and how long each list is (default: 10)")
    c.add_argument("--json", action="store_true", help="the same as JSON, with every smell of each list")
    c.set_defaults(fn=cmd_compare)


def add_ask_parsers(sub: argparse._SubParsersAction) -> None:
    """Register the commands that answer a question: `fixes`, `report`, `stats`, `diagnose` and `compare`, in that order."""
    fx = sub.add_parser("fixes", help="the usual fix of each kind of code smell, the lines the blocks carry")
    fx.add_argument("names", nargs="*", metavar="smell", help="only these smells (default: all)")
    fx.add_argument("--json", action="store_true", help="the same as JSON")
    fx.set_defaults(fn=cmd_fixes)
    r = sub.add_parser("report", help="what broom stopped, what was fixed and what went through, over a period")
    r.add_argument("paths", nargs="*", help="limit to these files or directories (default: the repo)")
    r.add_argument("--since", type=broom_version, metavar="VERSION",
                   help="only the lines written by this broom version or a later one (default: the whole record)")
    r.add_argument("--all", action="store_true",
                   help="every repo, not only this one, but those in a temporary folder")
    r.add_argument("--json", action="store_true", help="the same as JSON")
    r.set_defaults(fn=cmd_report)
    s = sub.add_parser("stats", help="size, tests, rot and history of the repo or some paths, as counts")
    s.add_argument("paths", nargs="*", help="limit to these files or directories (default: the repo)")
    s.add_argument("--top", type=int, default=10, help="how long each list is (default: 10)")
    s.add_argument("--commits", type=int, default=CHURN_COMMITS,
                   help=f"how many of the last commits history looks at (default: {CHURN_COMMITS})")
    s.add_argument("--json", action="store_true", help="the same as JSON")
    s.set_defaults(fn=cmd_stats)
    add_diagnosis_parsers(sub)
