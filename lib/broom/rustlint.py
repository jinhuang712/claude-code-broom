"""What clippy and rustc say, read as smells: which lint stands for which smell, the thresholds clippy runs with, and
what a message holds that its text alone doesn't (the name of a dead item, whether an unused variable is a parameter).
realtree.py runs clippy and keeps the findings on lines a change added."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from .config import DEAD_CODE

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
}
RUST_FLAGS = [flag for lint in RUST_LINTS if lint.startswith("clippy::") for flag in ("-W", lint)]
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
FN_NAME = re.compile(r"\bfn\s+(\w+)")
SIZE = re.compile(r"\((\d+)/\d+\)")  # "(8/7)": the size, then the threshold
FN_BEFORE = re.compile(r"\bfn\s+\w+\s*(?:<[^;{}]*>)?\s*$")  # what ends just before a function's parameter list
LOOKBACK = 1000


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


def in_parameters(source: str, line: int, col: int) -> bool:
    """Whether the place in `source` (1-based line and column, as rustc counts) is in a function's parameter list,
    not in its body or a closure's: the nearest `(` that nothing closes before the place follows `fn name`."""
    rows = source.splitlines(keepends=True)[:line]
    if not rows:
        return False
    head = "".join(rows[:-1]) + rows[-1][:col - 1]
    depth = 0
    for i in range(len(head) - 1, -1, -1):
        if head[i] == ")":
            depth += 1
        elif head[i] == "(" and depth:
            depth -= 1
        elif head[i] == "(":
            return bool(FN_BEFORE.search(head[max(0, i - LOOKBACK):i]))
    return False


def read(metric: str, message: dict, span: dict, source: str, soft: Dict[str, int]) -> Optional[Tuple[str, int]]:
    """What a message says of one of its primary spans, as the name of what has the smell and its size; None when
    the span isn't the smell (an unused variable that isn't a parameter). `source` is the span's file."""
    line = int(span["line_start"])
    if metric == DEAD_CODE:
        return highlighted(span), 1
    if metric == "deprecated_api":
        return message.get("message", ""), 1
    if metric == "unused_params" and not in_parameters(source, line, int(span["column_start"])):
        return None
    if metric == "nesting":  # the message names no depth, and clippy lints only the outermost block past it
        return "function", thresholds(soft)["nesting"]
    size = SIZE.search(message.get("message", ""))
    name = FN_NAME.search((source.splitlines()[line - 1:line] or [""])[0])
    return (name[1] if name else "function"), int(size[1]) if size else 1
