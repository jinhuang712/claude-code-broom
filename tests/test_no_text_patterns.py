"""No check reads code by a text pattern (goal R6, design 9): every regular expression in lib/broom reads a tool's
output, a path, a command, a setting, the text of one token a syntax tree already isolated, or a key that only
matches a thing to itself across versions. Each is listed here with what it reads; a new one fails until it is."""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Set, Tuple

LIB = Path(__file__).resolve().parent.parent / "lib" / "broom"
RE_CALLS = {"compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split"}
HELPERS = {"number", "match", "quoted_name"}  # reading.py's helpers, which take a pattern and run it

TOOL = "tool output"
PATH = "a path"
COMMAND = "a command"
SETTING = "a setting"
TOKEN = "one token's text"
IDENTITY = "an identity key"

# (module, where: the enclosing function or class.method, or the name a module-level pattern is bound to) -> what it
# reads, and one short reason.
ALLOWED: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("clones", "failure_note"): (TOOL, "jscpd's error text"),
    ("commitgate", "claim"): (IDENTITY, "a tool-use id made safe as a file name"),
    ("compare", "tools_in"): (TOOL, "the words of a broom note"),
    ("coverage", "GO_BLOCK"): (TOOL, "a line of Go's coverage profile"),
    ("depcruise", "blind_why"): (TOOL, "the version a package.json beside the tool gives"),
    ("dependencies", "REMOVED"): (TOOL, "a line of go mod's output"),
    ("dependencies", "go_version_error"): (TOOL, "the Go version go.mod or the toolchain names"),
    ("doctor", "check_repo_file"): (SETTING, "comments in .broom.json"),
    ("edithook", "SERENA_ONE_FILE"): (TOOL, "the name of the tool a hook reports"),
    ("edithook", "SERENA_MANY_FILES"): (TOOL, "the name of the tool a hook reports"),
    ("gitcmd", "ASSIGNMENT"): (COMMAND, "the Bash parser, issue I6"),
    ("gitcmd", "VAR_REF"): (COMMAND, "the Bash parser, issue I6"),
    ("gitcmd", "HEREDOC"): (COMMAND, "the Bash parser, issue I6"),
    ("gitcmd", "REDIRECTION"): (COMMAND, "the Bash parser, issue I6"),
    ("gitcmd", "_commit_in_unquotable"): (COMMAND, "the Bash parser, issue I6"),
    ("gitutil", "ChangedLines.HUNK"): (TOOL, "a hunk header of git diff"),
    ("jsmeasure", "read_oxlint"): (TOOL, "an oxlint rule code"),
    ("jsmeasure", "read_oxlint/quoted_name"): (TOOL, "an oxlint message"),
    ("jsmeasure", "oxlint_value/number"): (TOOL, "an oxlint message"),
    ("langlint", "VET_TYPE_ERROR"): (TOOL, "a go vet line"),
    ("langlint", "SWIFT_ERROR"): (TOOL, "a swift build line"),
    ("langlint", "SWIFT_BUILD_ERROR"): (TOOL, "a swift build line"),
    ("langlint", "NO_TEST_FRAMEWORK"): (TOOL, "a swift build line"),
    ("langlint", "ANSI"): (TOOL, "colour codes in a tool's output"),
    ("ledger", "note_tool"): (TOOL, "the words of a broom note"),
    ("ledger", "covers"): (TOOL, "the words of a broom note"),
    ("lsp", "major_version"): (TOOL, "a language server's --version"),
    ("maintained", "GENERATED"): (TOKEN, "a comment on a file's first lines, from its tree"),
    ("measure", "ruff_name/quoted_name"): (TOOL, "a ruff message"),
    ("measure", "measure_python/number"): (TOOL, "a ruff message"),
    ("measure", "golangci_read/number"): (TOOL, "a golangci-lint message"),
    ("measure", "golangci_read/match"): (TOOL, "a golangci-lint message"),
    ("measure", "measure_swift/number"): (TOOL, "a SwiftLint reason"),
    ("reading", "Reader.add/match"): (IDENTITY, "a row's line names its function, to match it across versions"),
    ("reading", "number"): (TOOL, "the helper: its callers pass a tool's message"),
    ("reading", "match"): (TOOL, "the helper: its callers pass a tool's message"),
    ("reading", "quoted_name/match"): (TOOL, "a tool's message"),
    ("realtree", "go_key"): (TOOL, "a staticcheck message"),
    ("rustcycles", "module_of"): (PATH, "a Rust file's path"),
    ("rustlint", "SIZE"): (TOOL, "a clippy message"),
    ("rustmeasure", "TEST_PATH"): (PATH, "a Rust file's path"),
    ("rustmeasure", "LITERAL"): (TOKEN, "a number literal ast-grep caught"),
    ("state", "parse_jsonc"): (SETTING, "a JSONC settings file"),
    ("state", "session_dir"): (IDENTITY, "a session id made safe as a file name"),
    ("statscan", "TODO_MARK"): (TOKEN, "a comment a tree isolated"),
    ("swiftcheck", "SWIFT_WARNING"): (TOOL, "a swift build line"),
    ("swiftcheck", "targets"): (TOOL, "a target name swift package describe gives"),
    ("swifttree", "ERROR"): (TOOL, "a swiftc diagnostic"),
    ("swifttree", "JSON_TOKEN"): (TOOL, "swiftc's JSON dump"),
    ("swifttree", "split_trees"): (TOOL, "swiftc's JSON dump"),
    ("testcmd", "INTERPRETER"): (COMMAND, "a program's name in a command"),
    ("testcmd", "RUNNER_NAME"): (PATH, "a test runner's file name"),
    ("testcmd", "UNDER_TESTS"): (PATH, "a test runner's path"),
    ("testcmd", "parts"): (COMMAND, "a shell command's separators"),
    ("testrot", "TEST_FILE"): (PATH, "a test file's path"),
    ("testrot", "PAIRING"): (PATH, "a test file's name"),
    ("testrot", "RUST_NOT_CODE"): (PATH, "a Rust file's path"),
    ("toolchain", "rust_edition"): (SETTING, "Cargo.toml"),
    ("turns", "turn_dir"): (IDENTITY, "a session id made safe as a file name"),
    ("vulnerabilities", "version_key"): (TOOL, "a version an audit tool reports"),
    ("waivers", "MARKERS"): (TOKEN, "a comment or Rust attribute a tree isolated"),
    ("waivers", "MARKUP_MARKERS"): (TOKEN, "a comment of a YAML, shell or HTML file a tree isolated"),
    ("weblint", "TSC_ROW"): (TOOL, "a tsc line"),
    ("weblint", "TSC_GLOBAL"): (TOOL, "a tsc line"),
    ("weblint", "_stylelint_findings"): (TOOL, "a stylelint message"),
}


def bound_name(node: ast.AST) -> Optional[str]:
    """The name an assignment binds, for a pattern compiled at module or class level."""
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return None
    names = [t.id for t in targets if isinstance(t, ast.Name)]
    return names[0] if names else None


def regex_call(node: ast.AST, helpers: Set[str]) -> Optional[str]:
    """`re.<call>` for a call of the re module; the name of one of reading.py's `helpers` for a call of it; else
    None."""
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "re" and f.attr in RE_CALLS:
        return f"re.{f.attr}"
    return f.id if isinstance(f, ast.Name) and f.id in helpers else None


@dataclass(frozen=True)
class Scope:
    """Where a node stands: the qualified name of the def or class around it, the name a module- or class-level
    assignment around it binds, and whether a function holds it (whose name then keys it)."""

    name: str = ""
    binding: Optional[str] = None
    in_function: bool = False

    def enter(self, node: ast.AST) -> "Scope":
        """The scope of a child `node`."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            inner = f"{self.name}.{node.name}" if self.name else node.name
            return Scope(inner, None, self.in_function or not isinstance(node, ast.ClassDef))
        return self if self.in_function else Scope(self.name, bound_name(node) or self.binding, False)

    def key(self, call: str) -> str:
        """The key of a regex `call` here: `where` for the re module, `where/helper` for a reading.py helper."""
        if self.in_function or not self.binding:
            where = self.name
        else:
            where = f"{self.name}.{self.binding}" if self.name else self.binding
        return where if call.startswith("re.") else f"{where}/{call}"


def regexes(path: Path) -> Iterator[Tuple[str, int]]:
    """(where, line) of each regular expression of the module at `path`: a function's are keyed by its qualified
    name, a module- or class-level pattern by the name it is bound to; a reading.py helper's call by
    `caller/helper`."""
    tree = ast.parse(path.read_text())
    imported = any(isinstance(n, ast.ImportFrom) and n.module == "reading" and any(a.name in HELPERS for a in n.names)
                   for n in ast.walk(tree))
    helpers = HELPERS if path.stem == "reading" or imported else set()
    todo: List[Tuple[ast.AST, Scope]] = [(tree, Scope())]
    while todo:
        node, scope = todo.pop()
        for child in ast.iter_child_nodes(node):
            inner = scope.enter(child)
            call = regex_call(child, helpers)
            if call:
                yield inner.key(call), child.lineno
            todo.append((child, inner))


class NoTextPatternTest(unittest.TestCase):
    def test_every_regular_expression_reads_something_other_than_code(self) -> None:
        seen = set()
        unknown = []
        for path in sorted(LIB.glob("*.py")):
            for where, line in regexes(path):
                seen.add((path.stem, where))
                if (path.stem, where) not in ALLOWED:
                    unknown.append(f"{path.stem}.py:{line} ({where})")
        self.assertEqual(unknown, [], "a regular expression must not read source code: read the code from its syntax "
                         "tree (decision 038), or, if it reads a tool's output, a path, a command, a setting or one "
                         "token a tree isolated, list it in ALLOWED with its reason")
        self.assertEqual(sorted(set(ALLOWED) - seen), [], "an entry in ALLOWED no longer matches a regex: remove it")

    def test_a_new_pattern_is_found_wherever_it_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mod = Path(tmp) / "m.py"
            mod.write_text('import re\nDEF = re.compile("def ")\nclass C:\n    HEAD = re.compile("x")\n'
                           '    def f(self, t):\n        return re.search("import", t)\n')
            self.assertEqual(sorted(regexes(mod)), [("C.HEAD", 4), ("C.f", 6), ("DEF", 2)])

    def test_re_is_only_ever_called_by_its_own_name(self) -> None:
        for path in sorted(LIB.glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "re", path.name)
                if isinstance(node, ast.Import):
                    self.assertEqual([a.asname for a in node.names if a.name == "re" and a.asname], [], path.name)

    def test_each_entry_says_what_it_reads(self) -> None:
        kinds = {TOOL, PATH, COMMAND, SETTING, TOKEN, IDENTITY}
        for key, (kind, reason) in ALLOWED.items():
            self.assertIn(kind, kinds, key)
            self.assertTrue(reason and len(reason) <= 80, key)


if __name__ == "__main__":
    unittest.main()
