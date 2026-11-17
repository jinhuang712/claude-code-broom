"""Known vulnerabilities in a repo's dependencies, from osv-scanner. It sends the names and versions of the packages in
the repo's lockfiles to a public database (api.osv.dev), so it runs only when the user asks for it with
`broom diagnose --vulnerabilities`: never in a hook and never without the flag. It is read from osv-scanner 2's JSON
(`results[].source`, `.packages[].package`, `.vulnerabilities[]`, `.groups[]`); a vulnerable package is listed per
lockfile with its version, the advisory ids and the version that fixes it, when the database gives one."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from .dependencies import Failed, execute, first_line, rel
from .needs import install_command, tools_db

TOOL = "osv-scanner"
FLAG = "--vulnerabilities"
EXIT_OK = (0, 1)  # 0: packages scanned, nothing known; 1: something known
EXIT_NO_PACKAGES = 128  # no lockfile or manifest found: not a failure
SENDS = ("osv-scanner sends the names and versions of the packages in the lockfiles to api.osv.dev "
         "(OSV, a public database)")
HINT = (f"Known vulnerabilities are not looked up: `broom diagnose {FLAG}` asks {TOOL}, which sends package names "
        "and versions to api.osv.dev (OSV, a public database).")
LEVELS = ("critical", "high", "medium", "low", "unknown")
CVSS_FLOORS = ((9.0, "critical"), (7.0, "high"), (4.0, "medium"), (0.1, "low"))  # a score's level, as CVSS bands it
LABELS = {"CRITICAL": "critical", "HIGH": "high", "MODERATE": "medium", "MEDIUM": "medium", "LOW": "low"}


def version_key(version: str) -> tuple:
    """The numbers in a version, to put versions in order; an approximation that serves semver and most others."""
    return tuple(int(n) for n in re.findall(r"\d+", version))


def cvss_level(score: object) -> Optional[str]:
    """The level a CVSS score of 0.1 to 10 stands for; None for anything else."""
    try:
        number = float(str(score))
    except ValueError:
        return None
    return next((name for floor, name in CVSS_FLOORS if number >= floor), None)


def record_level(record: dict) -> Optional[str]:
    """The level a record's `database_specific.severity` gives it (GitHub's advisories say CRITICAL, HIGH, MODERATE or
    LOW); None when it has none. Its `severity` list holds CVSS vectors, which give no score without a calculator."""
    label = (record.get("database_specific") or {}).get("severity")
    return LABELS.get(str(label).upper()) if label else None


def fixed_versions(record: dict, package: dict) -> List[str]:
    """The versions a record says fix `package`: the `fixed` events of its ranges that affect that package's name."""
    name = str(package.get("name", "")).lower()
    found = []
    for affected in record.get("affected") or []:
        if str((affected.get("package") or {}).get("name", "")).lower() == name:
            for span in affected.get("ranges") or []:
                found += [str(e["fixed"]) for e in span.get("events") or [] if e.get("fixed")]
    return found


def group_row(group: dict, records: Dict[str, dict], package: dict) -> dict:
    """One distinct vulnerability of a package, from its group: its record ids and aliases, a summary, its level, and
    the versions that fix it, those above the package's own version when there are any."""
    mine = [records[i] for i in group.get("ids") or [] if i in records]
    levels = [record_level(r) for r in mine]
    level = cvss_level(group.get("max_severity")) or next((x for x in levels if x), "unknown")
    fixed = sorted({v for r in mine for v in fixed_versions(r, package)}, key=version_key)
    newer = [v for v in fixed if version_key(v) > version_key(str(package.get("version", "")))]
    ids = sorted(group.get("ids") or [])
    aliases = sorted(({a for r in mine for a in r.get("aliases") or []} | set(group.get("aliases") or [])) - set(ids))
    return {"ids": ids, "aliases": aliases,
            "summary": next((r["summary"] for r in mine if r.get("summary")), ""), "severity": level,
            "fixed": newer or fixed}


def package_row(entry: dict) -> dict:
    """One vulnerable package of a lockfile: its name, version, ecosystem, its worst level, the version that fixes all
    the vulnerabilities that have a fix known, and its vulnerabilities."""
    package = entry.get("package") or {}
    records = {r["id"]: r for r in entry.get("vulnerabilities") or [] if isinstance(r, dict) and r.get("id")}
    groups = entry.get("groups") or [{"ids": [i]} for i in records]  # without groups each record stands alone
    rows = [group_row(g, records, package) for g in groups]
    worst = min((r["severity"] for r in rows), key=LEVELS.index, default="unknown")
    fixes = [r["fixed"][0] for r in rows if r["fixed"]]
    return {"name": package.get("name", ""), "version": package.get("version", ""),
            "ecosystem": package.get("ecosystem", ""), "severity": worst,
            "fixed_in": max(fixes, key=version_key) if fixes else "", "vulnerabilities": rows}


def lockfile_rows(repo: Path, data: object) -> List[dict]:
    """The lockfiles osv-scanner found vulnerable packages in, each with those packages."""
    results = data.get("results") if isinstance(data, dict) else None
    out = []
    for result in results or []:
        source = result.get("source") or {}
        packages = [package_row(p) for p in result.get("packages") or [] if p.get("vulnerabilities")]
        if packages:
            out.append({"lockfile": rel(repo, repo / str(source.get("path", ""))), "type": source.get("type", ""),
                        "packages": packages})
    return out


def counts(lockfiles: List[dict]) -> Dict[str, int]:
    """How many distinct vulnerabilities there are of each level, over every package of every lockfile."""
    found = {level: 0 for level in LEVELS}
    for lockfile in lockfiles:
        for package in lockfile["packages"]:
            for v in package["vulnerabilities"]:
                found[v["severity"]] += 1
    return found


def result(status: str, **more: object) -> dict:
    """The data of a vulnerability scan that was asked for."""
    return {"asked": True, "tool": TOOL, "status": status, "sends": SENDS, "install": "", "error": "",
            "lockfiles": [], "severity": {}, "vulnerable_packages": 0, **more}


def scan(repo: Path) -> dict:
    """Run osv-scanner on the repo and read what it says. Not installed, failed and nothing to scan are statuses of
    their own, never an error of broom's."""
    exe = shutil.which(TOOL)
    if not exe:
        return result("not installed", install=install_command(tools_db()[TOOL]))
    try:
        rc, out, err = execute([exe, "scan", "source", "-r", str(repo), "--format", "json"], repo)  # five minutes
        if rc == EXIT_NO_PACKAGES:
            return result("no packages")
        if rc not in EXIT_OK:
            raise Failed(first_line(out, err))
        lockfiles = lockfile_rows(repo, json.loads(out) if out.strip() else {})
    except ValueError:
        return result("failed", error=first_line(out, err))
    except Failed as e:
        return result("failed", error=str(e))
    return result("ok", lockfiles=lockfiles, severity=counts(lockfiles),
                  vulnerable_packages=sum(len(f["packages"]) for f in lockfiles))


def section(repo: Path, *, asked: bool) -> dict:
    """The diagnosis's vulnerabilities data: the scan when it was asked for, else only the fact that the flag exists.
    Nothing else starts osv-scanner."""
    if not asked:
        return {"asked": False, "tool": TOOL, "flag": FLAG}
    return scan(repo)


# ---------------------------------------------------------------- the report


def severity_line(data: dict) -> str:
    """`3 vulnerable package(s) in 2 lockfile(s); 1 critical, 2 high`, or that none is known."""
    if not data["vulnerable_packages"]:
        return "no known vulnerability in the packages of the lockfiles"
    shown = [f"{n} {level}" for level, n in data["severity"].items() if n]
    return (f"{data['vulnerable_packages']} vulnerable package(s) in {len(data['lockfiles'])} lockfile(s); "
            + ", ".join(shown))


def lockfile_lines(lockfile: dict) -> List[str]:
    """One lockfile's vulnerable packages as a table under its path."""
    from .statsview import table

    rows = [[p["name"], p["version"], p["severity"], ", ".join(i for v in p["vulnerabilities"] for i in v["ids"]),
             p["fixed_in"] or "-"] for p in lockfile["packages"]]
    body = table(["package", "version", "worst", "advisories", "fixed in"], rows, left=(0, 1, 2, 3, 4))
    return [f"  {lockfile['lockfile']}", *(f"  {row}" for row in body)]


def lines(data: dict) -> List[str]:
    """What the Dependencies section says of vulnerabilities: one line that the flag exists when it wasn't given, else
    what is sent where, then the result."""
    if not data["asked"]:
        return [f"  {HINT}"]
    out = [f"  {data['sends']}."]
    if data["status"] == "not installed":
        return out + [f"  not measured: {TOOL} is not installed (`{data['install']}`)"]
    if data["status"] == "failed":
        return out + [f"  {TOOL} failed: {data['error']}"]
    if data["status"] == "no packages":
        return out + [f"  {TOOL} found no lockfile or manifest to check"]
    out.append(f"  {severity_line(data)}")
    for lockfile in data["lockfiles"]:
        out += ["", *lockfile_lines(lockfile)]
    return out
