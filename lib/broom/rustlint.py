"""What clippy and rustc say, read as smells: which lint stands for which smell, the thresholds clippy runs with, and
what a message holds that its text alone doesn't (the name of a dead item, whether an unused variable is a parameter).
realtree.py runs clippy and keeps the findings on lines a change added. The functions and parameters a message points
at are read from the file's syntax tree (`defaults/sg/rules/rust-fn.yml`), as rustmeasure.rust_tree gives it."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .config import DEAD_CODE
from .setters import snake_setter
from .syntax import Match

# The lints, by the smell they find. clippy's are asked for with -W; rustc's warn on their own, so a crate that allows
# them keeps them off. `unused_variables` stands for unused parameters: read() drops the variables that aren't.
RUST_LINTS = {
    "clippy::too_many_arguments": "params", "clippy::fn_params_excessive_bools": "bool_params",
    "clippy::too_many_lines": "function_lines", "clippy::cognitive_complexity": "complexity",
    "clippy::excessive_nesting": "nesting",
    "clippy::dbg_macro": "debug_output", "clippy::print_stdout": "debug_output",
    "clippy::print_stderr": "debug_output", "clippy::unwrap_used": "type_escape",
    "clippy::allow_attributes_without_reason": "suppression",
    "clippy::todo": "todo", "clippy::unimplemented": "todo",
    # `let _ = f();` on a #[must_use] value, in practice a Result: the nearest lint to an error dropped on the floor.
    # It can't tell a deliberate ignore from a swallowed error, so smells.py makes it a hint in Rust.
    "clippy::let_underscore_must_use": "swallowed_error",
    "dead_code": DEAD_CODE, "unused_variables": "unused_params",
    "deprecated": "deprecated_api",  # a call to an item marked #[deprecated]; the message holds its note
    "clippy::map_err_ignore": "broad_catch",  # `.map_err(|_| ...)`: the error is replaced unread
    "missing_docs": "missing_docs",  # a public item, or the crate, with no doc comment
}
# rustc's lints that are off unless asked for, like clippy's.
RUSTC_ASKED = ("missing_docs",)
RUST_FLAGS = [flag for lint in RUST_LINTS if lint.startswith("clippy::") or lint in RUSTC_ASKED
              for flag in ("-W", lint)]
# The limits clippy takes, one threshold per lint, so it gets the soft one and the message says how far past it went.
# They come from a clippy.toml in a directory of broom's own, so the project's is never read and nothing is written
# into the crate. Tests are never built (`cargo clippy` leaves #[cfg(test)] and tests/ out), so a test may be long,
# unwrap, print and leave todo!() behind; the allow-*-in-tests lines only back that up.
SOFT_LIMITS = ("params", "function_lines", "complexity", "nesting")
RUST_CONFIG = """too-many-arguments-threshold = {params}
too-many-lines-threshold = {function_lines}
cognitive-complexity-threshold = {complexity}
excessive-nesting-threshold = {nesting}
max-fn-params-bools = 0
allow-unwrap-in-tests = true
allow-print-in-tests = true
allow-dbg-in-tests = true
"""
SIZE = re.compile(r"\((\d+)/\d+\)")  # "(8/7)": the size, then the threshold (in the message, not the source)


def thresholds(soft: Dict[str, int]) -> Dict[str, int]:
    """What clippy.toml holds for the soft limits `soft`. excessive_nesting lints a block nested at least this deep
    (the function body is level one), so the block of a nesting past the soft limit is `soft + 1`."""
    return {**{name: soft[name] for name in SOFT_LIMITS}, "nesting": soft["nesting"] + 1}


def config_text(soft: Dict[str, int]) -> str:
    """The clippy.toml broom runs clippy with."""
    return RUST_CONFIG.format(**thresholds(soft))


def highlighted(span: dict) -> str:
    """The text a diagnostic's span marks, on its first line: the name of a dead item."""
    row = (span.get("text") or [{}])[0]
    return row.get("text", "")[row.get("highlight_start", 1) - 1:row.get("highlight_end", 1) - 1]


def in_parameters(tree: List[Match], line: int, name: str) -> bool:
    """Whether `name` on `line` of a file with the syntax-tree matches `tree` is a parameter of a function, not a
    local or a closure's parameter."""
    return any(m.rule == "rust-fn-param" and m.line == line and m.caught.get("P") == name for m in tree)


def fn_name(tree: List[Match], line: int) -> str:
    """The name of the function that starts on `line` of a file with the syntax-tree matches `tree`."""
    return next((m.caught["NAME"] for m in tree if m.rule == "rust-fn-item" and m.line == line), "function")


def fn_span(tree: List[Match], line: int) -> int:
    """How many lines the function that starts on `line` of a file with the syntax-tree matches `tree` takes, from
    its first line through its closing brace; 0 when the tree has none there."""
    return next((m.lines for m in tree if m.rule == "rust-fn-item" and m.line == line), 0)


def read(metric: str, message: dict, span: dict, tree: List[Match], soft: Dict[str, int]) -> Optional[Tuple[str, int]]:
    """What a message says of one of its primary spans, as the name of what has the smell and its size; None when
    the span isn't the smell (an unused variable that isn't a parameter, a setter's boolean). `tree` holds the span's file's matches."""
    line = int(span["line_start"])
    if metric == DEAD_CODE:
        return highlighted(span), 1
    if metric == "deprecated_api":
        return message.get("message", ""), 1
    if metric == "unused_params" and not in_parameters(tree, line, highlighted(span)):
        return None
    if metric == "bool_params" and snake_setter(fn_name(tree, line)):
        return None  # a setter's boolean is no flag (decision 042): `set` or `set_…`, its name from the tree
    if metric == "nesting":  # the message names no depth, and clippy lints only the outermost block past it
        return "function", thresholds(soft)["nesting"]
    size = SIZE.search(message.get("message", ""))
    return fn_name(tree, line), int(size[1]) if size else 1
