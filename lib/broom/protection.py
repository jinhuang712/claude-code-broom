"""`broom doctor --checks`: which checks run in this repo, language by language, which don't for lack of a tool and the
command that turns each one on, and what broom checks with nothing installed at all.

A row is built from the doctor's own diagnosis (its items, which say whether each tool is there and runs) and from what
each check rests on, which `SPECS` writes down from the code that runs the check. Nothing is started that the doctor
doesn't start: the few tools the doctor doesn't ask about are looked up by name, as it looks up its own."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .config import repo_config, setting
from .doctor import MARKS
from .gate import display
from .needs import DEFAULTS_DETAIL, LANG_NAMES, Diagnosis, Item, install_command, tools_db
from .toolchain import css_linters, js_formatter, js_linters, resolve_bin

READ = "read by broom"  # the tool of a check that needs none: broom reads the code or the repo itself
ON, OFF, NONE = "on", "off", "none"
ANY_LANGUAGE = "any"  # the language of a check that holds for every language
SMELLS_OFF = "the smells setting is off"
NEEDED = "needed once"  # how the doctor says a tool is wanted only after formatting is switched on
DASH = "–"
GAP = "  "  # between the columns of a row
BARE_HEADER = "With no tool installed, broom still checks:"
OTHER_HEADER = "Beside the languages:"  # gaps of the repo itself: git's own hook, a broken .broom.json

FORMAT, LINT, TYPES, SMELLS = "format", "lint", "type check", "smells"
DUPLICATES, CYCLES, SERVER = "duplicate and dead code", "cycles", "diagnostics as Claude edits"


@dataclass(frozen=True)
class Need:
    """A tool a check rests on, as the doctor's items name it: their role and tool ("" for any tool of the role), and
    what the check loses without it. `anywhere` is for an item the doctor files under whichever language it found first
    (jscpd serves them all)."""
    role: str
    tool: str = ""
    lost: str = ""
    anywhere: bool = False

    def matches(self, item: dict, langs: Tuple[str, ...]) -> bool:
        """Whether `item` is this need's: of the languages the row reads, with its role and tool."""
        of_language = self.anywhere or item["lang"] in langs
        return of_language and item["role"] == self.role and self.tool in ("", item["tool"])


@dataclass(frozen=True)
class Spec:
    """One check of a language. `needs` are what it rests on (none: broom reads the code itself, and `tool` says what
    to call it). `none` is why broom has no such check here; `absent`, why it doesn't apply when the doctor has no item
    for any of the needs. A `smell` check goes with the `smells` setting."""
    check: str
    needs: Tuple[Need, ...] = ()
    tool: str = ""
    none: str = ""
    absent: str = ""
    smell: bool = False


@dataclass
class Row:
    """One line of the protection list: a check of a language, whether it runs (`on`, `off` for lack of a tool, or
    `none` where broom has no such check), with what, or why not and the command that turns it on."""
    language: str
    check: str
    status: str
    tool: str = ""
    why: str = ""
    fix: str = ""


def server(tool: str) -> Spec:
    """The language-server check: the server, and no other plugin starting one for the same files."""
    return Spec(SERVER, (Need("lsp", tool), Need("plugin")))


JSCPD = Need("smells", "jscpd", "duplicate and dead code aren't found", anywhere=True)
JSCPD_DUPLICATES = Need("smells", "jscpd", "duplicate code isn't found", anywhere=True)
DEAD = "dead code isn't found"
SMELLS_GO_RUST = "function length, nesting, complexity, parameters and occurrence smells aren't measured"
JS_OWN_RULES = ("flag parameters, long classes, module state, commented-out code and missing doc comments "
                "aren't measured")
JS_NO_OXLINT = "TS/JS smells aren't measured (broom looks for oxlint at the repo root)"
NO_PYTHON_TYPES = "broom's sweep has none; pyright reports type errors as Claude edits"
WEB = (
    Spec(FORMAT, (Need("format"),)),
    Spec(LINT, (Need("lint"),)),
    Spec(SMELLS, none="no smell tool for CSS: only file length and duplicates are measured"),
    Spec(DUPLICATES, (JSCPD_DUPLICATES,), tool="jscpd (duplicates only)", smell=True),
    server("vscode-css-language-server"),
)
SPECS: Dict[str, Tuple[Spec, ...]] = {
    "go": (
        Spec(FORMAT, (Need("format", "gofmt"),)),
        Spec(LINT, (Need("lint", "golangci-lint"),)),
        Spec(TYPES, (Need("types", "go"),), tool="go vet"),
        Spec(SMELLS, (Need("lint", "golangci-lint", SMELLS_GO_RUST),), smell=True),
        Spec(DUPLICATES, (JSCPD_DUPLICATES, Need("lint", "golangci-lint", DEAD)),
             tool="jscpd, golangci-lint (dead code)", smell=True),
        Spec(CYCLES, none="the Go compiler refuses import cycles"),
        server("gopls"),
    ),
    "js": (
        Spec(FORMAT, (Need("format"),)),
        Spec(LINT, (Need("lint", "oxlint"), Need("lint", "eslint"), Need("lint", "biome"),
                    Need("lint", "tsgolint", "oxlint's type-aware rules don't run"))),
        Spec(TYPES, (Need("types", "tsc"),), absent="no tsconfig.json, so there is nothing for tsc to check"),
        Spec(SMELLS, (Need("smells", "oxlint", JS_NO_OXLINT), Need("smells", "node", JS_OWN_RULES)),
             tool="oxlint, broom's own rules on node", smell=True),
        Spec(DUPLICATES, (JSCPD,), tool="jscpd", smell=True),
        Spec(CYCLES, (Need("smells", "oxlint", "import cycles aren't found"),
                      Need("smells", "dependency-cruiser", "cycles between folders aren't found")),
             tool="oxlint, dependency-cruiser (folders, with TypeScript below 7)", smell=True),
        server("typescript-language-server"),
    ),
    "rust": (
        Spec(FORMAT, (Need("format", "rustfmt"),)),
        Spec(LINT, (Need("lint", "cargo-clippy"),)),
        Spec(TYPES, (Need("types", "cargo"), Need("lint", "cargo-clippy", "compile errors aren't found")),
             tool="cargo clippy"),
        Spec(SMELLS, (Need("lint", "cargo-clippy", SMELLS_GO_RUST),), tool="cargo clippy, rustc", smell=True),
        Spec(DUPLICATES, (JSCPD_DUPLICATES, Need("lint", "cargo-clippy", DEAD)), tool="jscpd, rustc (dead code)",
             smell=True),
        Spec(CYCLES, none="broom reads no Rust imports"),
        server("rust-analyzer"),
    ),
    "py": (
        Spec(FORMAT, (Need("format", "ruff format"), Need("lint", "ruff", "Python isn't formatted")),
             tool="ruff format"),
        Spec(LINT, (Need("lint", "ruff"),)),
        Spec(TYPES, none=NO_PYTHON_TYPES),
        Spec(SMELLS, (Need("lint", "ruff", "complexity, parameters, nesting and occurrence smells aren't measured"),),
             tool="ruff, read by broom", smell=True),
        Spec(DUPLICATES, (JSCPD,), tool="jscpd", smell=True),
        Spec(CYCLES, tool=READ, smell=True),
        server("pyright-langserver"),
    ),
    "css": WEB,
    "scss": WEB,
    "less": WEB,
    "swift": (
        Spec(FORMAT, (Need("format"),)),
        Spec(LINT, (Need("lint", "swiftlint"),)),
        Spec(TYPES, (Need("types", "swift"),), tool="swift build",
             absent="no Package.swift: broom doesn't build an Xcode project"),
        Spec(SMELLS, (Need("lint", "swiftlint", "function and type length, parameters, complexity and occurrence "
                                                "smells aren't measured"),), smell=True),
        Spec(DUPLICATES, (JSCPD_DUPLICATES,), tool="jscpd (duplicates only)", smell=True),
        Spec(CYCLES, none="broom reads no Swift imports"),
        server("sourcekit-lsp"),
    ),
}
# A dialect's rows read the CSS items too: the formatter and the server are shared, and stylelint is the linter.
FAMILY = {"scss": ("scss", "css"), "less": ("less", "css")}
# What needs no tool, read from the code or from git alone: (check, the languages it covers or None for all, whether
# the smells setting turns it off).
SOME_SMELLS = ("py", "js", "go", "rust", "css", "scss", "less", "swift")
BARE = (
    ("file length", SOME_SMELLS, True),
    ("function and class length", ("py",), True),
    ("nested ternaries", ("py",), True),
    ("import and folder cycles", ("py",), True),
    ("skipped tests", ("py", "js", "go", "rust", "swift"), True),
    ("code files with no test by name", ("py", "js", "go", "swift"), True),
    ("check-up: lint suppressions, skipped tests, old TODOs", None, True),
    ("broom stats: sizes, tests, rot, history", None, False),
)


# ---------------------------------------------------------------- the rows


def unique(texts: Iterable[str]) -> List[str]:
    """`texts` without repeats, in order."""
    return list(dict.fromkeys(texts))


def phrase(need: Need, item: dict) -> str:
    """Why `item`, a tool the check needs, stops it: the doctor's own finding, and what the check loses."""
    tool, status, detail = item["tool"], item["status"], item["detail"]
    if status == "off":
        return f"{tool} is {detail}" if detail.startswith(NEEDED) else detail or f"{tool} is off"
    if status == "conflict":
        text = f"{tool} {detail}"
    elif status == "broken":
        text = f"{tool} doesn't run" + (f": {detail}" if detail else "")
    else:  # what the check loses says more than the doctor's detail, and the defaults' is no news
        shown = detail not in ("", DEFAULTS_DETAIL) and not need.lost
        text = f"{tool} is not installed" + (f" ({detail})" if shown else "")
    where = f" in {item['project']}" if item["project"] not in ("", ".") else ""
    return f"{text}{where}" + (f", so {need.lost}" if need.lost else "")


def one_row(lang: str, spec: Spec, items: List[dict], *, smells_on: bool) -> Optional[Row]:
    """The row for one check of `lang`, or None when the doctor's items can't say and the check has no `absent`."""
    if spec.none or (spec.smell and not smells_on):
        return Row(lang, spec.check, NONE, why=spec.none or SMELLS_OFF)
    langs = FAMILY.get(lang, (lang,))
    found = [(n, i) for n in spec.needs for i in items if n.matches(i, langs)]
    if spec.needs and not found:
        return Row(lang, spec.check, NONE, why=spec.absent) if spec.absent else None
    bad = [(n, i) for n, i in found if i["status"] != "ok"]
    if not bad:
        return Row(lang, spec.check, ON, spec.tool or ", ".join(unique(i["tool"] for _, i in found)) or READ)
    fixes = unique(i["fix"] for _, i in bad if i["fix"])
    return Row(lang, spec.check, OFF, ", ".join(unique(i["tool"] for _, i in bad)),
               "; ".join(unique(phrase(n, i) for n, i in bad)), " && ".join(fixes))


def deps_roles(item: dict, repo: Path) -> List[str]:
    """The checks a project's missing dependency stops: a linter's `lint`, a formatter's `format`, and biome's by what
    its config switches on."""
    css = item["lang"] == "css"
    probe = repo / item["project"] / ("_.css" if css else "_.ts")
    linters = {tool.split("-")[0] for tool, _ in (css_linters if css else js_linters)(probe, repo)}
    formatter = js_formatter(probe, repo)
    return [role for role, used in ((LINT, linters), (FORMAT, {formatter[0]} if formatter else set()))
            if item["tool"] in used]


def split_deps(items: List[dict], repo: Path) -> List[dict]:
    """`items` with each `deps` item (a configured tool whose package isn't installed) turned into one per check it
    stops, so that a row finds it with the tool's other findings."""
    out = []
    for item in items:
        if item["role"] == "deps":
            out += [{**item, "role": role} for role in deps_roles(item, repo)]
        else:
            out.append(item)
    return out


def css_formats(repo: Path, languages: Dict[str, List[str]]) -> List[Item]:
    """The formatter of each CSS project that the doctor doesn't ask about: it looks for one only where CSS has none to
    find, outside a JS project. Found by the project's config, as the formatter itself finds it."""
    diagnosis, out = Diagnosis(repo, {}), []
    for rel in languages.get("css", []):
        project = repo / rel
        found = js_formatter(project / "_.css", repo)
        if found and resolve_bin(found[0], project, repo):
            out.append(Item("css", "format", found[0], "ok", rel, f"project {found[0]} config"))
        elif found:
            out.append(diagnosis.deps_missing("css", found[0], found[1]))
        elif rel in languages.get("js", []):
            out.append(Item("css", "format", "oxfmt", "off", rel, "no formatter config, so broom doesn't format CSS",
                            f"broom init {rel}"))
    return out


def oxlint_item(repo: Path) -> Item:
    """The oxlint the smell scan runs: found from the repo root, whichever linter the projects use for linting."""
    found = resolve_bin("oxlint", repo, repo)
    return Item("js", "smells", "oxlint", "ok" if found else "missing", fix=install_command(tools_db().get("oxlint", {})))


def extra_items(repo: Path, languages: Dict[str, List[str]]) -> List[Item]:
    """The tools that checks rest on and that the diagnosis of each project doesn't ask about: the formatter of each CSS
    project, and the oxlint of the TS/JS smell scan, whichever linter the projects use. The doctor counts them as gaps."""
    out = css_formats(repo, languages)
    if "js" in languages and setting("smells", repo) != "off":
        out.append(oxlint_item(repo))
    return out


def language_rows(lang: str, items: List[dict], *, smells_on: bool) -> List[Row]:
    """The rows of one language, in the order of its checks."""
    rows = [one_row(lang, spec, items, smells_on=smells_on) for spec in SPECS[lang]]
    return [r for r in rows if r]


def bare_rows(languages: List[str], *, smells_on: bool) -> List[Row]:
    """The checks that need no tool, for the repo's languages; those of the smell scan are left out when it is off."""
    out = []
    for check, langs, smell in BARE:
        if smell and not smells_on:
            continue
        out += [Row(ANY_LANGUAGE, check, ON, READ)] if langs is None else [
            Row(lang, check, ON, READ) for lang in languages if lang in langs]
    return out


# ---------------------------------------------------------------- the list


class Protection:
    """What protects a repo: a row per check of each language it has, and the checks that need no tool."""

    def __init__(self, repo: Path, rows: List[Row], bare: List[Row], other: List[Row]) -> None:
        self.repo, self.rows, self.bare, self.other = repo, rows, bare, other

    def records(self) -> List[dict]:
        """The rows as the `checks` of `broom doctor --json`: the language ones, the repo's own gaps, then those
        that need no tool."""
        return [asdict(r) for r in self.rows + self.other + self.bare]

    def text(self) -> str:
        """The list as `broom doctor --checks` prints it: a block per language, then what needs no tool."""
        width = max([len(r.check) for r in self.rows + self.other] or [0])
        out = [f"broom doctor --checks: {display(self.repo)}"]
        out += [] if self.rows else ["", "Languages: none found"]
        for lang in unique(r.language for r in self.rows):
            out += ["", LANG_NAMES[lang]] + [row_line(r, width) for r in self.rows if r.language == lang]
        if self.other:
            out += ["", OTHER_HEADER] + [row_line(r, width) for r in self.other]
        if self.bare:
            out += ["", BARE_HEADER] + bare_lines(self.bare)
        return "\n".join(out)


def row_line(row: Row, width: int) -> str:
    """One row as text: its mark and check, then the tool, or why not (and the command) or why none."""
    if row.status == ON:
        mark, rest = MARKS["ok"], row.tool
    elif row.status == OFF:
        mark, rest = MARKS["missing"], GAP.join(x for x in (row.why, row.fix) if x)
    else:
        mark, rest = DASH, row.why
    return f"  {mark} {row.check.ljust(width)}{GAP}{rest}".rstrip()


def bare_lines(rows: List[Row]) -> List[str]:
    """The checks that need no tool as text, one line each with the languages it covers."""
    where: Dict[str, List[str]] = {}
    for r in rows:
        where.setdefault(r.check, []).append("every language" if r.language == ANY_LANGUAGE else LANG_NAMES[r.language])
    width = max(len(check) for check in where)
    return [f"  {MARKS['ok']} {check.ljust(width)}{GAP}{', '.join(langs)}" for check, langs in where.items()]


def other_rows(items: List[dict]) -> List[Row]:
    """The doctor's gaps that are no check of a language, such as git's own hook: they fail the doctor too, so the
    list names them, each as the doctor does."""
    return [Row(i["lang"], f"{i['lang']} {i['role']}", OFF, i["tool"], i.get("detail") or i["status"], i.get("fix") or "")
            for i in items if i["lang"] not in SPECS and i["status"] != "ok"]


def off_row(repo: Path) -> List[Row]:
    """The smells the repo's .broom.json turns off one by one (`smells_off`), which the rows above still show as
    measured: one row that names them."""
    off = repo_config(repo).get("smells_off")
    names = [str(n) for n in off] if isinstance(off, list) else []
    return [Row(ANY_LANGUAGE, "smells off", NONE, why=f"turned off in .broom.json: {', '.join(names)}")] if names else []


def protection(repo: Path, result: dict) -> Protection:
    """The protection list for `repo` from its doctor `result`: the doctor's items, split by the check each stops and
    added to where a check rests on a tool the doctor doesn't ask about."""
    languages = result["languages"]
    smells_on = setting("smells", repo) != "off"
    items = split_deps(result["items"], repo)
    rows = [r for lang in languages if lang in SPECS for r in language_rows(lang, items, smells_on=smells_on)]
    other = other_rows(result["items"]) + (off_row(repo) if smells_on else [])
    return Protection(repo, rows, bare_rows(list(languages), smells_on=smells_on), other)
