"""Runs the test files at once, each in a process of its own, and gives the verdict `python3 -m unittest discover -s
tests` would give.

    python3 tests/run.py [-j N] [pattern ...]

A pattern is part of a file's name (`doctor`, `test_smells`, `commit*`); with none, every `tests/test*.py` runs.
Each file runs as `python3 -m unittest <module>` with `tests/` on the path, as discovery has it, so each gets the
data directory of its own that tests/isolation.py gives a process. The longest files start first, by the seconds
the last run kept in the system temp directory, so that the long ones don't end up alone at the end.

One line comes as each file ends, then the full output of every file that failed, then a summary in unittest's own
words. It exits 0 when every file passed, 1 when one did not, and 2 when no file was found."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
FILE_TIMEOUT = 600  # seconds a file may run before it counts as failed
MAX_JOBS = 4  # on 18 cores -j 4 took 39 s, 6 and 8 took 42 and 41: the longest file, 40 s alone, is the floor
CACHE = Path(tempfile.gettempdir()) / f"broom-test-seconds-{os.getuid()}.json"
# The words of unittest's verdict line, in its order.
WORDS = ("failures", "errors", "skipped", "expected failures", "unexpected successes")
PASSING_CODES = (0, 5)  # 5: what Python 3.12 and later exit with when a file holds no tests
RAN = re.compile(r"^Ran (\d+) tests? in [\d.]+s$", re.MULTILINE)
VERDICT = re.compile(r"^(OK|FAILED|NO TESTS RAN)(?: \((.*)\))?$", re.MULTILINE)
LIVE: set = set()  # the processes running, so that an interrupt can end them


@dataclass
class Result:
    """What one test file did."""

    name: str
    ok: bool = False
    ran: int = 0
    seconds: float = 0.0
    counts: Counter = field(default_factory=Counter)
    output: str = ""
    why: str = ""  # set when the file did not end as unittest does: a crash or a timeout
    timed_out: bool = False


def say(text: str = "") -> None:
    """Write a line to stdout at once."""
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def default_jobs() -> int:
    """How many files run at once: half the cores, at least 2 and at most MAX_JOBS."""
    return max(2, min(MAX_JOBS, (os.cpu_count() or 4) // 2))


def find_files(patterns: Sequence[str]) -> List[Path]:
    """The test files discovery would find, narrowed to those whose name holds a pattern."""
    wanted = [f"*{Path(p).name.removesuffix('.py')}*" for p in patterns]
    return [p for p in sorted(TESTS.glob("test*.py")) if not wanted or any(fnmatchcase(p.stem, w) for w in wanted)]


def load_seconds() -> Dict[str, float]:
    """The seconds each file took in the last runs; empty when nothing was kept or it can't be read."""
    try:
        data = json.loads(CACHE.read_text())
        return {k: float(v) for k, v in data.items()}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def save_seconds(took: Dict[str, float]) -> None:
    """Keep the seconds of this run beside the older ones. The file is replaced whole, so two runs at once never
    leave half a file, and a run that can't write it loses only the order of the next one."""
    merged = {k: v for k, v in {**load_seconds(), **took}.items() if (TESTS / k).exists()}
    tmp = ""
    try:
        fd, tmp = tempfile.mkstemp(dir=CACHE.parent, prefix=CACHE.name + ".")
        with os.fdopen(fd, "w") as f:
            json.dump(merged, f)
        os.replace(tmp, CACHE)
    except OSError:
        if tmp:
            Path(tmp).unlink(missing_ok=True)


def longest_first(files: List[Path], known: Dict[str, float]) -> List[Path]:
    """The files in the order to start them: a file with no seconds kept first, as it may be long, then the longest."""
    return sorted(files, key=lambda p: (known.get(p.name, float("inf")), p.stat().st_size), reverse=True)


def end(proc: subprocess.Popen) -> None:
    """End a test process with everything it started in its session."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        proc.kill()


def read_verdict(text: str) -> Optional[Tuple[int, bool, Counter]]:
    """The tests run, whether they passed and the counts of unittest's verdict line, read from the last `Ran` line
    and the verdict after it; None when there is none, as when the file crashed."""
    ran = list(RAN.finditer(text))
    verdict = VERDICT.search(text, ran[-1].end()) if ran else None
    if not ran or not verdict:
        return None
    counts: Counter = Counter()
    for part in (verdict.group(2) or "").split(", "):
        word, _, number = part.partition("=")
        if number.isdigit():
            counts[word] = int(number)
    return int(ran[-1].group(1)), verdict.group(1) != "FAILED", counts


def start_file(path: Path, out) -> subprocess.Popen:
    """Start `python3 -m unittest <module>` for a test file, with `tests/` on the path as discovery has it."""
    path_var = os.pathsep.join(filter(None, [str(TESTS), os.environ.get("PYTHONPATH", "")]))
    return subprocess.Popen([sys.executable, "-m", "unittest", path.stem], cwd=ROOT,
                            env={**os.environ, "PYTHONPATH": path_var}, stdin=subprocess.DEVNULL, stdout=out,
                            stderr=subprocess.STDOUT, start_new_session=True)


def wait_for(path: Path) -> Tuple[int, str, bool]:
    """Run one test file; its exit code, its output and whether it was ended at the timeout. The output goes to a
    file, so that a daemon a test left behind can't keep this waiting by holding a pipe."""
    code, timed_out = 0, False
    with tempfile.TemporaryFile() as out:
        proc = start_file(path, out)
        LIVE.add(proc)
        try:
            code = proc.wait(timeout=FILE_TIMEOUT)
        except subprocess.TimeoutExpired:
            end(proc)
            code, timed_out = proc.wait(), True
        finally:
            LIVE.discard(proc)
        out.seek(0)
        return code, out.read().decode(errors="replace"), timed_out


def run_file(path: Path) -> Result:
    """Run one test file and say how it ended: as unittest does, or by a crash or a timeout, which count as one
    error."""
    start = time.monotonic()
    code, text, timed_out = wait_for(path)
    verdict = read_verdict(text)
    ran, ok, counts = verdict or (0, False, Counter())
    why = ""
    if timed_out:
        why = f"timed out after {FILE_TIMEOUT} s and was ended"
    elif verdict is None:
        why = f"ended with code {code} and no verdict"
    elif ok and code not in PASSING_CODES:
        why = f"ended with code {code} after a verdict of OK"
    if why and not counts["failures"] + counts["errors"]:
        counts["errors"] += 1
    return Result(path.name, ok and not why, ran, time.monotonic() - start, counts, text, why, timed_out)


def report_line(r: Result, width: int) -> str:
    """The line for a file that ended: its verdict, the tests it ran and skipped, and its seconds."""
    return (f"{'ok' if r.ok else 'FAILED':<7} {r.name:<{width}} {r.ran:>4} tests {r.counts['skipped']:>3} skipped "
            f"{r.seconds:>6.1f}s")


def run_all(files: List[Path], jobs: int) -> List[Result]:
    """Run the files, `jobs` at a time in the order given, and say each as it ends."""
    width, results = max(len(p.name) for p in files), []
    pool = ThreadPoolExecutor(max_workers=jobs)
    try:
        for future in as_completed([pool.submit(run_file, p) for p in files]):
            results.append(future.result())
            say(report_line(results[-1], width))
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        for proc in list(LIVE):
            end(proc)
        raise
    pool.shutdown()
    return results


def show_failures(results: List[Result]) -> None:
    """The whole output of every file that did not pass."""
    for r in sorted(results, key=lambda x: x.name):
        if not r.ok:
            say("\n" + "=" * 70 + f"\nFAILED {r.name}" + (f": {r.why}" if r.why else ""))
            say("=" * 70)
            say(r.output.rstrip())


def show_summary(results: List[Result], seconds: float) -> bool:
    """The summary in unittest's words; whether everything passed."""
    ran, totals = sum(r.ran for r in results), Counter()
    for r in results:
        totals.update(r.counts)
    ok = all(r.ok for r in results)
    words = ", ".join(f"{w}={totals[w]}" for w in WORDS if totals[w])
    verdict = "OK" if ok else "FAILED"
    say("\n" + "-" * 70 + f"\nRan {ran} test{'' if ran == 1 else 's'} in {seconds:.1f}s\n")
    say(verdict + (f" ({words})" if words else ""))
    return ok


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the test files at once and give the verdict; the exit code."""
    parser = argparse.ArgumentParser(description="Run each test file in a process of its own, several at a time.")
    parser.add_argument("-j", "--jobs", type=int, default=default_jobs(), help="files at once (default: %(default)s)")
    parser.add_argument("patterns", nargs="*", help="run the files whose name holds one of these")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("-j takes at least 1")
    files = find_files(args.patterns)
    if not files:
        sys.stderr.write("no test file found\n")
        return 2
    start = time.monotonic()
    try:
        results = run_all(longest_first(files, load_seconds()), args.jobs)
    except KeyboardInterrupt:
        sys.stderr.write("interrupted\n")
        return 130
    save_seconds({r.name: r.seconds for r in results if not r.timed_out})
    show_failures(results)
    return 0 if show_summary(results, time.monotonic() - start) else 1


if __name__ == "__main__":
    sys.exit(main())
