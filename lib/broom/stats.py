"""`broom stats`: the counts a session would otherwise write a throwaway script for, in four sections: size, tests, rot
and history. It needs git and nothing else. The files are those every broom command reads (`hotspots.repo_files`, less
dependencies, build output and generated code), read once (statscan); history is one `git log` and the TODOs' age a
bounded `git blame` (statsgit). A question it can't answer comes back with a `note` saying what is missing."""

from __future__ import annotations

from collections import Counter, defaultdict
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .coverage import section as coverage_section
from .hotspots import repo_files
from .maintained import GENERATED, Maintained
from .statscan import Facts, scan
from .syntax import MISSING
from .statsgit import DAY, OLD_DAYS, blame, history, top_counts
from .testrot import needs_test, stem_of, tested
from .toolchain import lang_of
from .treefacts import SG_LANGS, sg_trees


def collect(repo: Path, paths: List[Path]) -> List[Facts]:
    """The facts of every code file within `paths` (the repo when empty): the files `repo_files` gives, less what nobody
    maintains here (dependencies, build output) and generated code, found by its header. ast-grep reads the trees of
    the Go and TS/JS files among them in one run."""
    read = texts(repo, paths)
    trees = sg_trees(repo, [rel for rel, lang, _ in read if lang in SG_LANGS], [])
    return [scan(rel, lang, text, trees.get(rel)) for rel, lang, text in read]


def texts(repo: Path, paths: List[Path]) -> List[Tuple[str, str, str]]:
    """(path from the root, language, text) of each code file `collect` reads."""
    keep = Maintained(repo)
    out = []
    for f in repo_files(repo, paths):
        lang = lang_of(f)
        try:
            rel = f.relative_to(repo).as_posix()
            text = f.read_text(errors="replace") if lang and keep(rel) else None
        except (OSError, ValueError):  # gone from the disk, or a link that leads out of the repo
            continue
        if lang and text is not None and not GENERATED.search("\n".join(text.splitlines()[:5])):
            out.append((rel, lang, text))
    return out


def ranked(counts: Dict[object, int], top: int, label: str = "count") -> List[dict]:
    """The `top` files with the highest counts, as `{"file": path, label: count}`."""
    return [{"file": name, label: n} for name, n in top_counts(counts, top)]


# ---------------------------------------------------------------- size


def folder_of(f: Facts) -> str:
    """The top-level folder of a file, `.` for a file at the root."""
    return f.rel.split("/")[0] if "/" in f.rel else "."


def totals(facts: List[Facts]) -> dict:
    """Files and non-blank lines of the `facts`, tests counted apart from the rest."""
    code = [f for f in facts if not f.test]
    tests = [f for f in facts if f.test]
    return {"files": len(code), "lines": sum(f.lines for f in code),
            "test_files": len(tests), "test_lines": sum(f.lines for f in tests)}


def breakdown(facts: List[Facts], key: Callable[[Facts], str], label: str) -> List[dict]:
    """`totals` per group of files, largest first; `key` names a file's group and `label` the key of that name."""
    groups: Dict[str, List[Facts]] = defaultdict(list)
    for f in facts:
        groups[key(f)].append(f)
    rows = [{label: name, **totals(group)} for name, group in groups.items()]
    return sorted(rows, key=lambda r: (-(r["lines"] + r["test_lines"]), r[label]))


def size_section(facts: List[Facts], top: int, note: Optional[str]) -> dict:
    """Lines by language and by top-level folder (the `top` largest), and the `top` longest files."""
    folders = breakdown(facts, folder_of, "folder")
    longest = sorted(facts, key=lambda f: (-f.lines, f.rel))[:top]
    return {"total": totals(facts), "languages": breakdown(facts, lambda f: f.lang, "language"),
            "folders": folders[:top], "more_folders": max(0, len(folders) - top),
            "longest": [{"file": f.rel, "lines": f.lines, "test": f.test} for f in longest], "note": note}


# ---------------------------------------------------------------- tests


def untested(facts: List[Facts]) -> Tuple[int, List[Facts]]:
    """How many code files have a test file named for them somewhere in `facts`, as the pairing goes by file name, and
    those that have none, the largest first. Files of a language with no such naming (CSS, Rust) are not counted."""
    named = tested((f.rel, f.lang) for f in facts)
    code = [f for f in facts if needs_test(f.rel, f.lang)]
    bare = [f for f in code if (f.lang, stem_of(f.rel)) not in named]
    return len(code), sorted(bare, key=lambda f: (-f.lines, f.rel))


def tests_section(repo: Path, facts: List[Facts], top: int, note: Optional[str]) -> dict:
    """Test files and cases, per language; the skipped ones with the `top` files holding most; the code files with no
    test file by name, with the `top` largest; and the coverage a report of the project's own test run shows."""
    groups: Dict[str, List[Facts]] = defaultdict(list)
    for f in facts:
        if f.test or f.cases or f.skipped:
            groups[f.lang].append(f)
    languages = [{"language": lang, "files": sum(f.test for f in fs), "cases": sum(f.cases for f in fs),
                  "skipped": sum(f.skipped for f in fs)} for lang, fs in sorted(groups.items())]
    skipped = {f.rel: f.skipped for f in facts if f.skipped}
    checked, bare = untested(facts)
    return {"files": sum(f.test for f in facts), "with_cases": sum(1 for f in facts if f.test and f.cases),
            "cases": sum(f.cases for f in facts), "skipped": sum(skipped.values()),
            "languages": languages, "skipped_files": ranked(skipped, top),
            "untested": {"count": len(bare), "of": checked,
                         "largest": [{"file": f.rel, "lines": f.lines} for f in bare[:top]]},
            "coverage": coverage_section(repo, {f.rel: f.lang for f in facts if not f.test}, top), "note": note}


# ---------------------------------------------------------------- rot


def todo_part(repo: Path, facts: List[Facts], top: int) -> dict:
    """TODO, FIXME, HACK and XXX comments: the total, how many of the lines git blame was asked about are past `OLD_DAYS`
    days, the `top` oldest of those with the day each was written, and the `top` files holding most. The files with
    most go to blame first, as the cap may cut the rest."""
    found = {f.rel: f.todos for f in facts if f.todos}
    counts = {rel: len(lines) for rel, lines in found.items()}
    blamed = blame(repo, [(rel, found[rel]) for rel, _ in top_counts(counts, len(found))])
    now = time.time()
    ages = sorted((when, rel, line) for rel, line, when in blamed.written)
    oldest = [{"file": rel, "line": line, "written": time.strftime("%Y-%m-%d", time.localtime(when)),
               "days": int((now - when) // DAY)} for when, rel, line in ages[:top]]
    return {"total": sum(counts.values()), "blamed": len(ages), "older_than_days": OLD_DAYS,
            "older": sum(now - when > OLD_DAYS * DAY for when, _, _ in ages), "oldest": oldest,
            "capped": blamed.capped, "files": ranked(counts, top)}


def unread_note(facts: List[Facts]) -> Optional[str]:
    """What a count leaves out when ast-grep couldn't read some files' trees; None when every file was read."""
    unread = sum(not f.read for f in facts)
    return f"{unread} Go or TS/JS files unread: {MISSING}" if unread else None


def rot_section(repo: Path, facts: List[Facts], top: int, note: Optional[str]) -> dict:
    """Lint suppressions by kind, with the `top` files holding most; the TODO comments; skipped tests as one number."""
    kinds = Counter(k for f in facts for k in f.suppressions)
    suppressed = {f.rel: len(f.suppressions) for f in facts if f.suppressions}
    return {"suppressions": {"total": sum(kinds.values()), "kinds": dict(kinds.most_common()),
                             "files": ranked(suppressed, top)},
            "todos": todo_part(repo, facts, top), "skipped_tests": sum(f.skipped for f in facts),
            "note": note or unread_note(facts)}


# ---------------------------------------------------------------- the report


def relative(repo: Path, path: Path) -> str:
    """`path` from the repo root (`.` for the root itself), or as it is when it lies outside."""
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return str(path)


def report(repo: Path, paths: List[Path], top: int, days: int, facts: Optional[List[Facts]] = None) -> dict:
    """The four sections for the code files within `paths` (the repo when empty): `size`, `tests`, `rot` and `history`
    over the last `days` days, with `files`, the number of files read. `facts` are those files read already, when a
    caller that needs them too has read them."""
    facts = collect(repo, paths) if facts is None else facts
    shown = [relative(repo, p) for p in paths]
    note = None if facts else "no code files " + (f"under {', '.join(shown)}" if shown else "in the repo")
    return {"repo": str(repo), "paths": shown, "files": len(facts), "days": days,
            "size": size_section(facts, top, note), "tests": tests_section(repo, facts, top, note or unread_note(facts)),
            "rot": rot_section(repo, facts, top, note),
            "history": history(repo, {f.rel for f in facts}, days, top, note)}
