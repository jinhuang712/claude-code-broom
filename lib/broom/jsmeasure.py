"""Smells in TS and JS, measured with oxlint: its own rules, and broom's for what it has none for."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Callable, List, Optional

from .config import SMELL_PRESENCE
from .gitutil import run
from .reading import TOOL_TIMEOUT, Limits, Reader, number, quoted_name
from .state import DEFAULTS
from .toolchain import resolve_bin

OXLINT_METRICS = {
    "max-lines-per-function": "function_lines", "max-params": "params", "max-depth": "nesting",
    "complexity": "complexity", "no-nested-ternary": "nested_ternary",
    "ban-ts-comment": "suppression", "no-empty": "swallowed_error", "no-useless-catch": "swallowed_error",
    "no-magic-numbers": "magic_numbers", "no-console": "debug_output", "no-warning-comments": "todo",
    "no-explicit-any": "type_escape", "no-non-null-assertion": "type_escape", "no-unused-vars": "unused_params",
    "require-to-throw-message": "broad_test_asserts",
}
OXLINT_CATEGORIES = ("correctness", "suspicious", "perf", "pedantic", "style", "restriction", "nursery")
OXLINT_MAGIC = {"ignore": [-1, 0, 1, 2], "ignoreArrayIndexes": True, "ignoreDefaultValues": True, "ignoreEnums": True}


def oxlint_config(lim: Limits) -> dict:
    whole = {"skipBlankLines": False, "skipComments": False}
    sized = {
        "max-lines-per-function": ["warn", {"max": lim["function_lines"][0], **whole}],
        "max-params": ["warn", {"max": lim["params"][0]}],
        "max-depth": ["warn", {"max": lim["nesting"][0]}],
        "complexity": ["warn", {"max": lim["complexity"][0]}],
    }
    present = {rule: "warn" for rule, metric in OXLINT_METRICS.items() if metric in SMELL_PRESENCE}
    return {"plugins": ["typescript", "jest"], "categories": {c: "off" for c in OXLINT_CATEGORIES},
            "rules": {**{rule_name(r): v for r, v in present.items()},
                      "no-magic-numbers": ["warn", OXLINT_MAGIC], "no-nested-ternary": "warn",
                      "no-unused-vars": ["warn", {"args": "all", "argsIgnorePattern": "^_"}], **sized}}


def oxlint_metric(rule: str, msg: str) -> Optional[str]:
    """The metric an oxlint finding stands for. no-unused-vars also reports variables and imports, which the
    project's own linter already covers, so only its parameters count."""
    metric = OXLINT_METRICS.get(rule)
    return None if metric == "unused_params" and not msg.startswith("Parameter") else metric


TS_RULES = {"ban-ts-comment", "no-explicit-any", "no-non-null-assertion"}
JEST_RULES = {"require-to-throw-message"}


def rule_name(rule: str) -> str:
    """The name oxlint takes a rule by: the TypeScript and Jest plugins' rules carry their plugin's."""
    if rule in TS_RULES:
        return f"typescript/{rule}"
    return f"jest/{rule}" if rule in JEST_RULES else rule


def oxlint_value(metric: str, msg: str) -> Optional[int]:
    if metric == "nested_ternary" or metric in SMELL_PRESENCE:
        return 1
    return number(r"complexity of (\d+)", msg) if metric == "complexity" else number(r"\((\d+)\)", msg)


def run_oxlint(r: Reader, exe: str, name: str, config: dict, rels: List[str]) -> List[dict]:
    """The findings of one oxlint run, with `config` written to a file named for `name`."""
    cfg = r.root.parent / f"{r.root.name}-{name}.json"
    cfg.write_text(json.dumps(config))
    rc, out, _ = run([exe, "-c", str(cfg), "-f", "json", "--no-error-on-unmatched-pattern", *rels], r.root,
                     timeout=TOOL_TIMEOUT)
    return r.json(rc, out, {}).get("diagnostics", [])


def read_oxlint(r: Reader, diagnostics: List[dict], metric_of: Callable[[str, str], Optional[str]]) -> None:
    """Add as rows the findings that `metric_of(rule, message)` gives a metric."""
    for d in diagnostics:
        rule = re.sub(r"^[\w-]+\(|\)$", "", d.get("code", ""))
        msg = d.get("message", "")
        metric = metric_of(rule, msg)
        if metric:
            line = int(((d.get("labels") or [{}])[0].get("span") or {}).get("line", 0))
            r.add(d.get("filename", ""), line, metric, oxlint_value(metric, msg), quoted_name(msg))


# broom's own oxlint rules (defaults/oxlint-rules.mjs), for what oxlint has none for. They are JS plugins, an alpha
# feature, so they run in a pass of their own: an old oxlint or a missing Node costs these two smells, no others.
BROOM_RULES = DEFAULTS / "oxlint-rules.mjs"
BROOM_RULE_METRICS = {"bool-params": "bool_params", "class-lines": "type_lines", "module-state": "globals",
                      "commented-code": "commented_code"}


def broom_rules_config(lim: Limits) -> dict:
    return {"jsPlugins": [str(BROOM_RULES)], "plugins": ["typescript"],
            "categories": {c: "off" for c in OXLINT_CATEGORIES},
            "rules": {"broom/bool-params": "warn", "broom/class-lines": ["warn", {"max": lim["type_lines"][0]}],
                      "broom/module-state": "warn", "broom/commented-code": "warn"}}


def broom_rule_metric(rule: str, _msg: str) -> Optional[str]:
    return BROOM_RULE_METRICS.get(rule)


def measure_js(r: Reader, rels: List[str], lim: Limits, start: Path) -> None:
    exe = resolve_bin("oxlint", start, start)
    if not exe:
        r.notes.append("missing:oxlint (npm i -g oxlint), so TS/JS smells aren't measured")
        return
    read_oxlint(r, run_oxlint(r, exe, "oxlint", oxlint_config(lim), rels), oxlint_metric)
    if shutil.which("node"):
        read_oxlint(r, run_oxlint(r, exe, "oxlint-rules", broom_rules_config(lim), rels),
                    broom_rule_metric)
    else:
        r.notes.append("node is missing, so boolean flag parameters and long classes in TS/JS aren't measured")
