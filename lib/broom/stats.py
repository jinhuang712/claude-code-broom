"""`broom stats`: the counts a session would otherwise write a throwaway script for, in four sections: size, tests, rot
and history. It needs git and nothing else. The files are those every broom command reads (`hotspots.repo_files`, less
dependencies, build output and generated code), read once (statscan); history is one `git log` (statsgit). Code files
make up size and tests; the YAML, shell, HTML and Markdown files read beside them add to rot alone. A question it
can't answer comes back with a `note` saying what is missing."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .codelines import code_lines
from .coverage import section as coverage_section
from .hotspots import repo_files
from .gitutil import git
from .maintained import Maintained, generated_among
from .mdlinks import known_paths
from .statscan import MD_LANG, OTHER_LANGS, Facts, link_facts, scan
from .syntax import MISSING
from .statsgit import history, top_counts
from .testrot import needs_test, stem_of, tested
from .toolchain import lang_of, markup_of
from .treefacts import MARKUP_LANGS, SG_LANGS, sg_trees


def collect(repo: Path, paths: List[Path]) -> List[Facts]:
    """The facts of every code file within `paths` (the repo when empty): the files `repo_files` gives, less what nobody
    maintains here (dependencies, build output) and generated code, found by its header, and with them the YAML, shell,
    HTML and Markdown files, read for their suppressions and links. ast-grep reads the trees of the Go, TS/JS, Rust,
    CSS, YAML, shell and HTML files among them in one run, and the comments of the code files in another, for the code
    lines."""
    read = texts(repo, paths)
    trees = sg_trees(repo, [rel for rel, lang, _ in read if lang in SG_LANGS or lang in MARKUP_LANGS], [])
    code = code_lines({rel: text for rel, lang, text in read if lang not in OTHER_LANGS}, [], repo)
    known = known_paths(existing(repo)) if any(lang == MD_LANG for _, lang, _ in read) else set()
    facts = [scan(rel, lang, text, trees.get(rel), len(code[rel]) if rel in code else 0) for rel, lang, text in read]
    return [link_facts(f, text, known) if lang == MD_LANG else f for f, (_, lang, text) in zip(facts, read)]


def existing(repo: Path) -> List[str]:
    """The paths of the repo's files a link may point at: tracked or not yet, with those git ignores and those gone
    from the disk left out. Not narrowed by `.broom.json`'s `exclude`: a file nobody checks can still be linked."""
    listed = git(["ls-files", "--cached", "--others", "--exclude-standard"], repo) or ""
    gone = set((git(["ls-files", "--deleted"], repo) or "").splitlines())
    return [n for n in listed.splitlines() if n and n not in gone]


def other_lang(path: Path) -> Optional[str]:
    """`yaml`, `shell`, `html` or `md` for a file read only for its suppressions or its links; None for any other."""
    return markup_of(path) or (MD_LANG if path.suffix.lower() == ".md" else None)


def texts(repo: Path, paths: List[Path]) -> List[Tuple[str, str, str]]:
    """(path from the root, language, text) of each file `collect` reads: code files, and those of `other_lang`."""
    keep = Maintained(repo)
    out = []
    for f in repo_files(repo, paths):
        lang = lang_of(f) or other_lang(f)
        try:
            rel = f.relative_to(repo).as_posix()
            text = f.read_text(errors="replace") if lang and keep(rel) else None
        except (OSError, ValueError):  # gone from the disk, or a link that leads out of the repo
            continue
        if lang and text is not None:
            out.append((rel, lang, text))
    made = generated_among(repo, {rel: text for rel, _, text in out})
    return [row for row in out if row[0] not in made]


def ranked(counts: Dict[object, int], top: int, label: str = "count") -> List[dict]:
    """The `top` files with the highest counts, as `{"file": path, label: count}`."""
    return [{"file": name, label: n} for name, n in top_counts(counts, top)]


# ---------------------------------------------------------------- size


def folder_of(f: Facts) -> str:
    """The top-level folder of a file, `.` for a file at the root."""
    return f.rel.split("/")[0] if "/" in f.rel else "."


def totals(facts: List[Facts]) -> dict:
    """Files and code lines of the `facts`, tests counted apart from the rest."""
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


def largest_files(repo: Path, paths: List[Path], top: int) -> List[dict]:
    """The `top` tracked files within `paths` (the repo when empty) with the most bytes, any kind of file, as `{"file":
    path, "bytes": size}`: the size on the disk, the file system's count. A file gone from the disk, or a link that
    leads out of the repo, is left out."""
    tracked = set((git(["ls-files"], repo) or "").splitlines())
    sizes: Dict[str, int] = {}
    for f in repo_files(repo, paths):
        try:
            rel = f.relative_to(repo).as_posix()
            if rel in tracked and f.is_file():
                sizes[rel] = os.stat(f).st_size
        except (OSError, ValueError):
            continue
    return ranked(sizes, top, "bytes")


def size_section(facts: List[Facts], top: int, note: Optional[str], largest: Optional[List[dict]] = None) -> dict:
    """Lines by language and by top-level folder (the `top` largest), the `top` longest files, and `largest`, the
    tracked files of most bytes (`largest_files`)."""
    folders = breakdown(facts, folder_of, "folder")
    longest = sorted(facts, key=lambda f: (-f.lines, f.rel))[:top]
    return {"total": totals(facts), "languages": breakdown(facts, lambda f: f.lang, "language"),
            "folders": folders[:top], "more_folders": max(0, len(folders) - top),
            "longest": [{"file": f.rel, "lines": f.lines, "test": f.test} for f in longest],
            "largest_files": largest or [], "note": note}


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


def todo_part(facts: List[Facts], top: int) -> dict:
    """TODO, FIXME, HACK and XXX comments: the total and the `top` files holding most."""
    counts = {f.rel: len(f.todos) for f in facts if f.todos}
    return {"total": sum(counts.values()), "files": ranked(counts, top)}


def unread_note(facts: List[Facts]) -> Optional[str]:
    """What a count leaves out when ast-grep couldn't read some files' trees; None when every file was read."""
    unread = sum(not f.read for f in facts)
    return f"{unread} files unread: {MISSING}" if unread else None


def counted_part(counts: Dict[str, int], top: int) -> dict:
    """A count per file as the rot section shows it: the total and the `top` files holding most."""
    return {"total": sum(counts.values()), "files": ranked(counts, top)}


def rot_section(facts: List[Facts], top: int, note: Optional[str]) -> dict:
    """Lint suppressions by kind, with the `top` files holding most; the TODO comments; skipped tests as one number;
    unsafe code and Markdown links to paths that don't exist, each with the files holding most."""
    kinds = Counter(k for f in facts for k in f.suppressions)
    suppressed = {f.rel: len(f.suppressions) for f in facts if f.suppressions}
    return {"suppressions": {"total": sum(kinds.values()), "kinds": dict(kinds.most_common()),
                             "files": ranked(suppressed, top)},
            "todos": todo_part(facts, top), "skipped_tests": sum(f.skipped for f in facts),
            "unsafe_code": counted_part({f.rel: f.unsafe for f in facts if f.unsafe}, top),
            "broken_links": counted_part({f.rel: len(f.broken_links) for f in facts if f.broken_links}, top),
            "note": note or unread_note(facts)}


# ---------------------------------------------------------------- the report


def relative(repo: Path, path: Path) -> str:
    """`path` from the repo root (`.` for the root itself), or as it is when it lies outside."""
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return str(path)


def report(repo: Path, paths: List[Path], top: int, last: int, facts: Optional[List[Facts]] = None) -> dict:
    """The four sections for the files within `paths` (the repo when empty): `size`, `tests`, `rot` and `history`
    over the last `last` commits, with `files`, the number of code files read. `facts` are those files read already,
    when a caller that needs them too has read them. Size, tests and history are of the code files; rot is of all."""
    facts = collect(repo, paths) if facts is None else facts
    code = [f for f in facts if f.code]
    shown = [relative(repo, p) for p in paths]
    note = None if code else "no code files " + (f"under {', '.join(shown)}" if shown else "in the repo")
    return {"repo": str(repo), "paths": shown, "files": len(code), "last_commits": last,
            "size": size_section(code, top, note or unread_note(code), largest_files(repo, paths, top)),
            "tests": tests_section(repo, code, top, note or unread_note(code)),
            "rot": rot_section(facts, top, note),
            "history": history(repo, {f.rel for f in code}, last, top, note)}
