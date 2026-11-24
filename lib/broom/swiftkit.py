"""The Swift toolchain's own tokenizer and structure, from SourceKit (sourcekitd, through ctypes): the tokens of a file
with their kinds (comment, string, identifier, keyword ...) and the tree of its declarations, calls and arguments,
each with its byte offset. It is what the compiler's parser reads, so a brace in a raw string or a `//` in a string
literal is never a comment or a block (decision 038).

`swiftc -dump-parse` gives the full tree but leaves comments out and gives an expression no place in the file; this
gives both. On macOS the requests go to SourceKit's own service, as SwiftLint's do, so a crash there costs an answer
and never this process; elsewhere they are served in this process. Without a toolchain that ships sourcekitd,
`open_text` gives None and the callers say so in a note.
"""

from __future__ import annotations

import bisect
import ctypes
import ctypes.util
import json
import itertools
import os
import shutil
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterator, List, Optional, Set, Tuple

from .gitutil import run

MISSING = "missing:sourcekitd (it comes with Xcode or a Swift toolchain), so Swift's comments, calls and parameters " \
          "aren't read"
KIND = "key.kind"
SUB = "key.substructure"


class Variant(ctypes.Structure):
    """sourcekitd_variant_t: three words, passed by value."""
    _fields_ = [("data", ctypes.c_uint64 * 3)]


def toolchain_lib() -> Optional[Path]:
    """The `lib` directory of the toolchain swiftc runs from: xcrun's on macOS, the one on the PATH elsewhere."""
    xcrun = shutil.which("xcrun")
    swiftc = run([xcrun, "--find", "swiftc"], Path.cwd(), timeout=15)[1].strip() if xcrun else None
    swiftc = swiftc or shutil.which("swiftc")
    return Path(os.path.realpath(swiftc)).parent.parent / "lib" if swiftc else None


def bind(lib: ctypes.CDLL) -> ctypes.CDLL:
    """`lib` with the C signatures of the sourcekitd calls used here."""
    p, s = ctypes.c_void_p, ctypes.c_char_p
    for name, res, args in (("sourcekitd_uid_get_from_cstr", p, [s]),
                            ("sourcekitd_request_dictionary_create", p, [p, p, ctypes.c_size_t]),
                            ("sourcekitd_request_dictionary_set_uid", None, [p, p, p]),
                            ("sourcekitd_request_dictionary_set_string", None, [p, p, s]),
                            ("sourcekitd_request_dictionary_set_int64", None, [p, p, ctypes.c_int64]),
                            ("sourcekitd_send_request_sync", p, [p]), ("sourcekitd_request_release", None, [p]),
                            ("sourcekitd_response_is_error", ctypes.c_bool, [p]),
                            ("sourcekitd_response_get_value", Variant, [p]),
                            ("sourcekitd_variant_json_description_copy", p, [Variant]),
                            ("sourcekitd_response_dispose", None, [p])):
        fn = getattr(lib, name)
        fn.restype, fn.argtypes = res, args
    lib.sourcekitd_initialize()
    return lib


@lru_cache(maxsize=None)
def library() -> Optional[ctypes.CDLL]:
    """sourcekitd, loaded and initialized once: the client of SourceKit's service on macOS, else the library that
    serves requests in this process; None when the toolchain has neither or it won't load."""
    lib = toolchain_lib()
    if lib is None:
        return None
    for path in (lib / "sourcekitd.framework" / "sourcekitd", lib / "libsourcekitdInProc.so"):
        if path.is_file():
            try:
                return bind(ctypes.CDLL(str(path)))
            except (OSError, AttributeError):
                return None
    return None


def request(kit: ctypes.CDLL, fields: dict) -> Optional[dict]:
    """Send one request of `fields` (a str value starting `source.` is a UID) and give its answer as JSON."""
    uid = kit.sourcekitd_uid_get_from_cstr
    req = kit.sourcekitd_request_dictionary_create(None, None, 0)
    for key, value in fields.items():
        if isinstance(value, int):
            kit.sourcekitd_request_dictionary_set_int64(req, uid(key.encode()), value)
        elif value.startswith("source."):
            kit.sourcekitd_request_dictionary_set_uid(req, uid(key.encode()), uid(value.encode()))
        else:
            kit.sourcekitd_request_dictionary_set_string(req, uid(key.encode()), value.encode())
    resp = kit.sourcekitd_send_request_sync(req)
    kit.sourcekitd_request_release(req)
    try:
        if kit.sourcekitd_response_is_error(resp):
            return None
        raw = kit.sourcekitd_variant_json_description_copy(kit.sourcekitd_response_get_value(resp))
        text = ctypes.string_at(raw).decode(errors="replace")
        libc().free(ctypes.c_void_p(raw))
        return json.loads(text)
    except ValueError:
        return None
    finally:
        kit.sourcekitd_response_dispose(resp)


@lru_cache(maxsize=None)
def libc() -> ctypes.CDLL:
    """The C library, to free what sourcekitd allocated."""
    return ctypes.CDLL(ctypes.util.find_library("c"))


@dataclass
class Token:
    """One token of the syntax map: its kind's last part (`comment`, `doccomment`, `identifier`, `keyword` ...), its
    byte offset and its text."""
    kind: str
    offset: int
    text: str


@dataclass
class Node:
    """A node of SourceKit's structure: its kind's last parts (`decl.function.free`, `expr.call` ...), name, byte
    offset and length, and its raw fields and children."""
    kind: str
    name: str
    offset: int
    length: int
    raw: dict
    children: List["Node"] = field(default_factory=list)

    def walk(self) -> Iterator["Node"]:
        """This node and every node under it, in source order."""
        yield self
        for child in self.children:
            yield from child.walk()


class Lines:
    """A file's bytes, with the line of any byte offset in them: SourceKit and swiftc both count in bytes."""
    data: bytes
    starts: List[int]

    def line(self, offset: int) -> int:
        """The 1-based line of the byte `offset`."""
        if not self.starts:
            self.starts = list(itertools.accumulate((len(row) + 1 for row in self.data.split(b"\n")[:-1]), initial=0))
        return bisect.bisect_right(self.starts, offset)


@dataclass
class SwiftFile(Lines):
    """A Swift file as SourceKit reads it: its bytes, tokens and structure, with a line for any byte offset."""
    data: bytes
    tokens: List[Token]
    root: Node
    starts: List[int] = field(default_factory=list)

    def within(self, node: Node) -> List[Token]:
        """The tokens inside `node`."""
        return [t for t in self.tokens if node.offset <= t.offset < node.offset + node.length]


def node(raw: dict) -> Node:
    """The structure node of SourceKit's `raw` dictionary, with its children."""
    kind = str(raw.get(KIND, "")).replace("source.lang.swift.", "")
    return Node(kind, str(raw.get("key.name", "")), int(raw.get("key.offset", 0)), int(raw.get("key.length", 0)), raw,
                [node(c) for c in raw.get(SUB) or []])


def parses(text: str) -> Optional[bool]:
    """Whether the Swift source `text` parses with no error; None without sourcekitd."""
    kit = library()
    if kit is None:
        return None
    name = f"broom-{id(text)}.swift"
    answer = request(kit, {"key.request": "source.request.editor.open", "key.name": name, "key.sourcetext": text,
                           "key.enablesyntaxmap": 0, "key.enablesubstructure": 0, "key.syntactic_only": 1,
                           "key.enablediagnostics": 1})
    request(kit, {"key.request": "source.request.editor.close", "key.name": name})
    return answer is not None and not any(str(d.get("key.severity", "")).endswith(".error")
                                          for d in answer.get("key.diagnostics") or [])


def open_text(text: str) -> Optional[SwiftFile]:
    """The tokens and structure of the Swift source `text`, read by syntax alone (nothing is built or resolved); None
    without sourcekitd."""
    kit = library()
    if kit is None:
        return None
    name = f"broom-{id(text)}.swift"
    answer = request(kit, {"key.request": "source.request.editor.open", "key.name": name, "key.sourcetext": text,
                           "key.enablesyntaxmap": 1, "key.enablesubstructure": 1, "key.syntactic_only": 1})
    request(kit, {"key.request": "source.request.editor.close", "key.name": name})
    if answer is None:
        return None
    data = text.encode()
    tokens = [Token(str(t.get(KIND, "")).replace("source.lang.swift.syntaxtype.", ""), int(t["key.offset"]),
                    data[t["key.offset"]:t["key.offset"] + t["key.length"]].decode(errors="replace"))
              for t in answer.get("key.syntaxmap") or []]
    return SwiftFile(data, tokens, node(answer))


@dataclass
class Comment:
    """A run of comments: its first line, the line it ends on, each comment's text, whether it is a run of `//`
    comments, and whether it stands on lines of its own, with no code before it."""
    line: int
    end: int
    texts: List[str]
    slashes: bool
    alone: bool = True


def comments(f: SwiftFile) -> List[Comment]:
    """The comments of `f`, from its tokens (doc comments left out): `//` comments alone on lines that follow one
    another make one run, and so does a comment SourceKit splits around a URL."""
    out: List[Comment] = []
    end, code = -1, 0  # where the last comment ended, and the line of the last token of code
    for t in f.tokens:
        line = f.line(t.offset)
        if not t.kind.startswith("comment"):
            code = line
            continue
        last = f.line(t.offset + len(t.text.encode().rstrip(b"\n")) - 1)
        if out and t.offset == end and not out[-1].texts[-1].endswith("\n"):  # a piece of one, as a URL is
            out[-1].texts[-1] += t.text
        elif out and out[-1].slashes and out[-1].alone and code != line and t.text.startswith("//") \
                and line == out[-1].end + 1:
            out[-1].texts.append(t.text)
        else:
            out.append(Comment(line, last, [t.text], t.text.startswith("//"), code != line))
        out[-1].end, end = max(out[-1].end, last), t.offset + len(t.text.encode())
    return out


def comment_lines(f: SwiftFile) -> List[Tuple[int, str]]:
    """Each line of each comment of `f`, doc comments included, as (line, its text with the comment sign): a block
    comment over three lines gives three, and the pieces SourceKit splits a comment into around a URL give one."""
    pieces: List[Token] = []
    for t in f.tokens:
        if "comment" not in t.kind:
            continue
        before = pieces[-1] if pieces else None
        if before and before.offset + len(before.text.encode()) == t.offset and not before.text.endswith("\n"):
            before.text += t.text
        else:
            pieces.append(Token(t.kind, t.offset, t.text))
    return [(f.line(t.offset) + n, text) for t in pieces for n, text in enumerate(t.text.rstrip("\n").split("\n"))]


def import_lines(text: str) -> Set[int]:
    """The lines of the Swift source `text` that hold an `import` keyword; none without SourceKit."""
    f = open_text(text)
    return {f.line(t.offset) for t in f.tokens if t.kind == "keyword" and t.text == "import"} if f else set()
