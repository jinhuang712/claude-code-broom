"""A minimal LSP client: just enough to ask a language server where the functions in a file are.

The servers are the ones in broom's own .lsp.json, the same Claude Code starts for diagnostics. A server that is
missing, fails or is too slow yields None, and callers fall back to changed lines: broom never guesses function
boundaries from indentation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Set, Tuple

from .common import PLUGIN_ROOT, boundary, find_up

FUNCTION_KINDS = {6, 9, 12}  # LSP SymbolKind: Method, Constructor, Function
PROJECT_MARKERS = {"go": ["go.mod"], "rust": ["Cargo.toml"], "py": ["pyproject.toml", "setup.py", "setup.cfg"],
                   "typescript": ["tsconfig.json", "package.json"], "javascript": ["tsconfig.json", "package.json"]}
Ranges = List[Tuple[int, int]]


def servers() -> Dict[str, Tuple[List[str], str]]:
    """File extension -> (server command line, languageId), from .lsp.json."""
    out: Dict[str, Tuple[List[str], str]] = {}
    try:
        config = json.loads((PLUGIN_ROOT / ".lsp.json").read_text())
    except (OSError, ValueError):
        return out
    for spec in config.values():
        cmd = [spec["command"], *spec.get("args", [])]
        for ext, language in spec.get("extensionToLanguage", {}).items():
            out[ext] = (cmd, language)
    return out


class Client:
    """One language server over stdio. Requests from the server (configuration, capability registration) get
    empty answers so it never waits on us."""

    def __init__(self, cmd: List[str], root: Path) -> None:
        self.proc = subprocess.Popen(cmd, cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL)
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.stdin: IO[bytes] = self.proc.stdin
        self.stdout: IO[bytes] = self.proc.stdout
        self.root = root
        self.next_id = 0
        self.results: Dict[int, dict] = {}
        self.done = threading.Condition()
        threading.Thread(target=self._read, daemon=True).start()

    def _send(self, msg: dict) -> None:
        body = json.dumps({"jsonrpc": "2.0", **msg}).encode()
        try:
            self.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            self.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def _read(self) -> None:
        out = self.stdout
        while True:
            length = 0
            while True:
                line = out.readline()
                if not line:
                    return
                if line in (b"\r\n", b"\n"):
                    break
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":")[1])
            msg = json.loads(out.read(length) or b"{}")
            if "method" in msg and "id" in msg:  # a request from the server
                params = msg.get("params") or {}
                result = [None] * len(params.get("items", [])) if msg["method"] == "workspace/configuration" else None
                self._send({"id": msg["id"], "result": result})
            elif "id" in msg:
                with self.done:
                    self.results[msg["id"]] = msg
                    self.done.notify_all()

    def request(self, method: str, params: dict, timeout: float) -> Any:
        self.next_id += 1
        rid = self.next_id
        self._send({"id": rid, "method": method, "params": params})
        with self.done:
            if not self.done.wait_for(lambda: rid in self.results, timeout):
                raise TimeoutError(method)
            msg = self.results.pop(rid)
        if "error" in msg:
            raise RuntimeError(msg["error"].get("message", method))
        return msg.get("result")

    def notify(self, method: str, params: dict) -> None:
        self._send({"method": method, "params": params})

    def start(self, timeout: float) -> None:
        uri = self.root.as_uri()
        self.request("initialize", {
            "processId": os.getpid(), "rootUri": uri, "workspaceFolders": [{"uri": uri, "name": self.root.name}],
            "capabilities": {"textDocument": {"documentSymbol": {"hierarchicalDocumentSymbolSupport": True}},
                             "workspace": {"configuration": True, "workspaceFolders": True}},
        }, timeout)
        self.notify("initialized", {})

    def close(self) -> None:
        try:
            self.request("shutdown", {}, 2)
            self.notify("exit", {})
            self.proc.wait(timeout=2)
        except (TimeoutError, RuntimeError, subprocess.TimeoutExpired):
            pass
        if self.proc.poll() is None:
            self.proc.kill()


def _lines(rng: dict) -> Tuple[int, int]:
    """An LSP range as 1-based inclusive lines; an end at column 0 of a later line stops the line before."""
    start, end = rng["start"], rng["end"]
    last = end["line"] if end.get("character", 0) > 0 or end["line"] == start["line"] else end["line"] - 1
    return start["line"] + 1, last + 1


def outermost_functions(symbols: list) -> Ranges:
    """Line ranges of the outermost functions and methods: a method, not its class; a function, not the closures
    inside it."""
    out: Ranges = []

    def walk(items: list) -> None:
        for s in items or []:
            if s.get("kind") in FUNCTION_KINDS and "range" in s:
                out.append(_lines(s["range"]))
            else:
                walk(s.get("children", []))

    if symbols and "location" in symbols[0]:  # flat SymbolInformation: drop functions nested in functions
        flat = [_lines(s["location"]["range"]) for s in symbols if s.get("kind") in FUNCTION_KINDS]
        return [r for r in flat if not any(o != r and o[0] <= r[0] and r[1] <= o[1] for o in flat)]
    walk(symbols)
    return out


def function_ranges(files: List[Path], timeout: float = 20) -> Dict[Path, Optional[Ranges]]:
    """Outermost function ranges per file; None where no language server answered."""
    table = servers()
    groups: Dict[Tuple[Tuple[str, ...], str, Path], List[Path]] = {}
    out: Dict[Path, Optional[Ranges]] = {f: None for f in files}
    for f in files:
        found = table.get(f.suffix.lower())
        if not found or not shutil.which(found[0][0]):
            continue
        cmd, language = found
        stop = boundary(f)
        key = "py" if language == "python" else language.replace("react", "")  # typescriptreact -> typescript
        marker = find_up(f.parent, PROJECT_MARKERS.get(key, []), stop)
        groups.setdefault((tuple(cmd), language, marker.parent if marker else stop), []).append(f)
    for (cmd, language, root), members in groups.items():
        client = None
        try:
            client = Client(list(cmd), root)
            client.start(timeout)
            for f in members:
                uri = f.as_uri()
                client.notify("textDocument/didOpen", {"textDocument": {
                    "uri": uri, "languageId": language, "version": 1, "text": f.read_text(errors="replace")}})
                symbols = client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}}, timeout)
                out[f] = outermost_functions(symbols if isinstance(symbols, list) else [])
        except (OSError, TimeoutError, RuntimeError, ValueError, KeyError):
            pass
        finally:
            if client:
                client.close()
    return out


def expand_to_functions(changed: Set[int], ranges: Ranges) -> Set[int]:
    """The changed lines plus every line of each function that holds one of them."""
    out = set(changed)
    for first, last in ranges:
        if any(first <= n <= last for n in changed):
            out.update(range(first, last + 1))
    return out
