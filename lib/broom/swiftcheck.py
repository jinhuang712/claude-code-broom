"""Deprecated calls in Swift, which only the compiler sees: the changed files of a SwiftPM package are type-checked
as the primary files of their target, and its `[#DeprecatedDeclaration]` warnings read.

The package is never built: its manifest is read with `swift package dump-package` into a scratch path of broom's
own, and the modules it depends on are read from its own .build, when a build left them there. Without them a call
into another target or package doesn't resolve, and only what the target itself and the SDK deprecate is seen.
Xcode projects have no manifest to read, so they aren't covered.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .gitutil import run
from .langlint import ANSI, SWIFT_ERROR
from .toolchain import SWIFT_EXTS, find_up

# The compiler's warning, worded as its error is: `/abs/File.swift:3:5: warning: 'old()' is deprecated: … [#Group]`.
SWIFT_WARNING = re.compile(SWIFT_ERROR.pattern.replace(" error: ", " warning: "))
DEPRECATED = "DeprecatedDeclaration"
# Where a build leaves the package's modules: SwiftPM's own build system, then Swift 6.4's swiftbuild.
MODULE_DIRS = (".build/debug/Modules", ".build/debug", ".build/out/Products/Debug")
SOURCE_DIRS = ("Sources", "Source", "src", "srcs")
MANIFEST_SECONDS = 30
Target = Tuple[str, Path, List[Path]]  # module name, directory, its Swift files


@lru_cache(maxsize=1)
def sdk_flags() -> Tuple[str, ...]:
    """The macOS SDK and the platform's XCTest, where xcrun finds them; nothing elsewhere, as on Linux."""
    xcrun = shutil.which("xcrun")
    if not xcrun:
        return ()
    _, sdk, _ = run([xcrun, "--sdk", "macosx", "--show-sdk-path"], Path.cwd(), timeout=15)
    _, platform, _ = run([xcrun, "--sdk", "macosx", "--show-sdk-platform-path"], Path.cwd(), timeout=15)
    flags: List[str] = ["-sdk", sdk.strip()] if sdk.strip() else []
    if platform.strip():
        dev = Path(platform.strip()) / "Developer"
        flags += ["-F", str(dev / "Library/Frameworks"), "-I", str(dev / "usr/lib")]
    return tuple(flags)


def target_dir(package: Path, target: dict) -> Optional[Path]:
    """Where a target's sources are: the path its manifest gives, else SwiftPM's default for its kind."""
    if target.get("path"):
        return package / target["path"]
    roots = ("Tests",) if target.get("type") == "test" else SOURCE_DIRS
    return next((package / root / target["name"] for root in roots if (package / root / target["name"]).is_dir()), None)


def targets(package: Path, swift: str, timeout: float) -> Optional[List[Target]]:
    """The Swift targets of `package` from its manifest, read into a scratch path that is thrown away; None when
    the manifest can't be read in time."""
    with tempfile.TemporaryDirectory(prefix="broom-swiftpm-") as scratch:
        rc, out, _ = run([swift, "package", "--scratch-path", scratch, "dump-package"], package,
                         timeout=min(timeout, MANIFEST_SECONDS))
    try:
        manifest = json.loads(out) if rc == 0 else None
    except ValueError:
        manifest = None
    if manifest is None:
        return None
    out_targets: List[Target] = []
    for t in manifest.get("targets") or []:
        where = target_dir(package, t)
        if where is None or t.get("type") in ("system", "binary", "plugin"):
            continue
        excluded = [where / e for e in t.get("exclude") or []]
        files = ([where / s for s in t["sources"]] if t.get("sources") else sorted(where.rglob("*.swift")))
        files = [f for f in files if f.suffix in SWIFT_EXTS and not any(e == f or e in f.parents for e in excluded)]
        out_targets.append((re.sub(r"\W", "_", t["name"]), where, files))
    return out_targets


def typecheck(swiftc: str, package: Path, target: Target, primary: List[Path], timeout: float) -> Tuple[Optional[int], str]:
    """`swiftc -frontend -typecheck` of the `primary` files with the rest of their target: nothing is written."""
    module, _, sources = target
    others = [f for f in sources if f not in primary]
    includes = [arg for d in MODULE_DIRS if (package / d).is_dir() for arg in ("-I", str(package / d))]
    args = [arg for f in primary for arg in ("-primary-file", str(f))] + [str(f) for f in others]
    rc, out, err = run([swiftc, "-frontend", "-typecheck", *args, "-module-name", module, *sdk_flags(), *includes],
                       package, timeout=timeout)
    return rc, ANSI.sub("", out + err)


def deprecations(out: str) -> List[Tuple[Path, int, str]]:
    """The deprecated-declaration warnings in the compiler's `out`: file, line and what it says."""
    found = []
    for row in out.splitlines():
        m = SWIFT_WARNING.match(row)
        if m and m["group"] == DEPRECATED:
            found.append((Path(m["file"]).resolve(), int(m["line"]), m["msg"].replace("'", "")))
    return found


def packages(repo: Path, rels: List[str]) -> Dict[Path, List[Path]]:
    """The changed Swift files of `rels` by the SwiftPM package they belong to; files in none are left out."""
    out: Dict[Path, List[Path]] = {}
    for rel in rels:
        f = (repo / rel).resolve()
        manifest = find_up(f.parent, ["Package.swift"], repo) if f.suffix in SWIFT_EXTS else None
        if manifest:
            out.setdefault(manifest.parent.resolve(), []).append(f)
    return out


def package_deprecations(package: Path, files: List[Path], timeout: Callable[[], float],
                         notes: List[str]) -> List[Tuple[Path, int, str]]:
    """The deprecated calls in `files` of one package, from one type check per target they are in."""
    swift, swiftc = shutil.which("swift"), shutil.which("swiftc")
    found: List[Tuple[Path, int, str]] = []
    if not swift or not swiftc or not timeout():
        return found
    for target in targets(package, swift, timeout()) or []:
        primary = [f for f in target[2] if f.resolve() in files]
        if not primary or not timeout():
            continue
        rc, out = typecheck(swiftc, package, target, primary, timeout())
        if rc is None:
            notes.append(f"timeout:swiftc measuring deprecated calls in {package} (a cold module cache?)")
            return found
        found += deprecations(out)
    return found


def swift_deprecated(repo: Path, rels: List[str], notes: List[str],
                     timeout: Callable[[], float]) -> List[Tuple[str, int, str]]:
    """The deprecated calls in the changed Swift files `rels` of SwiftPM packages, as (rel, line, what it says);
    `timeout` gives what the scan's budget has left."""
    out = []
    for package, files in packages(repo, rels).items():
        if not timeout():
            notes.append("timeout:the time of this scan ran out before swiftc measured smells")
            break
        for path, line, what in package_deprecations(package, files, timeout, notes):
            if path in files:
                out.append((path.relative_to(repo.resolve()).as_posix(), line, what))
    return out
