"""Python's tests that assert nothing, read from the file's tree (`ast`): the extreme of `broad_test_asserts`. A test
asserts when it holds an `assert`, a `raise`, a call whose last name starts `assert`, `expect` or `fail`,
`pytest.raises`, `pytest.warns` or `pytest.fail`, or a call of a function of the same file that asserts, itself or
through another such function. A helper from another file may still assert, so a finding is a guess."""

from __future__ import annotations

import ast
from typing import Dict, Iterator, List, Set

from .treefacts import decorator_skip

ASSERTING_CALLS = ("assert", "expect", "fail")
PYTEST_CHECKS = {"raises", "warns", "fail"}
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def call_name(n: ast.Call) -> str:
    """The last name of the function a call calls: `assertEqual` for `self.assertEqual(...)`."""
    return n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")


def checks(node: ast.AST, helpers: Set[str]) -> bool:
    """Whether `node` holds anything that can fail a test, a call of one of the file's asserting `helpers` among it."""
    for n in ast.walk(node):
        if isinstance(n, (ast.Assert, ast.Raise)):
            return True
        if isinstance(n, ast.Call):
            name, owner = call_name(n), getattr(n.func, "value", None)
            if name.startswith(ASSERTING_CALLS) or name in helpers or (
                    name in PYTEST_CHECKS and getattr(owner, "id", "") == "pytest"):
                return True
    return False


def asserting_helpers(tree: ast.Module) -> Set[str]:
    """The names of the file's functions and methods that assert, directly or through another one of them."""
    defs: Dict[str, List[ast.AST]] = {}
    for n in ast.walk(tree):
        if isinstance(n, FUNCTIONS):
            defs.setdefault(n.name, []).append(n)
    found: Set[str] = set()
    grew = True
    while grew:
        new = {name for name, nodes in defs.items() if name not in found and any(checks(n, found) for n in nodes)}
        found |= new
        grew = bool(new)
    return found


def own_nodes(node: ast.AST) -> Iterator[ast.AST]:
    """The nodes of a function's own body, without those of a function or a lambda inside it."""
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, (*FUNCTIONS, ast.Lambda, ast.ClassDef)):
            yield child
            yield from own_nodes(child)


def returns_value(node: ast.AST) -> bool:
    """Whether the function `node` returns a value: a factory or a helper, no test (pytest warns at one that does)."""
    return any(isinstance(n, ast.Return) and n.value is not None for n in own_nodes(node))


def python_tests(tree: ast.Module) -> Iterator[ast.AST]:
    """The tests of a Python file that run: a `test_*` function at module level, and a `test*` method of a class
    there. A test a decorator skips with no condition is a skipped test, whatever it asserts, and a function that
    returns a value is none."""
    found = [node for node in tree.body if isinstance(node, FUNCTIONS) and node.name.startswith("test_")]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            found += [m for m in node.body if isinstance(m, FUNCTIONS) and m.name.startswith("test")]
    yield from (n for n in found
                if all(decorator_skip(d) is not False for d in n.decorator_list) and not returns_value(n))


def empty_tests(tree: ast.Module) -> Iterator[ast.AST]:
    """The tests of the file `tree` that assert nothing."""
    helpers = asserting_helpers(tree)
    return (n for n in python_tests(tree) if not checks(n, helpers))
