"""`broom diagnose --vulnerabilities`: osv-scanner, which sends package names and versions to a public database, so that
nothing starts it without the flag. Its JSON is read from a fixture written from the output its documentation gives
(tests/fixtures/deps/osv.json): osv-scanner is not installed on the machine these tests were written on, so the
parsing was never run against the tool itself. The tool is a small script on PATH that logs where it ran and how."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from support import BROOM, BroomCase

from broom import vulnerabilities as vuln
from broom.dependencies import RUN_SECONDS

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "deps" / "osv.json"
PYPROJECT = '[project]\nname = "x"\nversion = "0"\n'
OFF = {"asked": False, "tool": "osv-scanner", "flag": "--vulnerabilities"}


def fixture() -> dict:
    """The fixture's JSON."""
    return json.loads(FIXTURE.read_text())


class ParseTest(unittest.TestCase):
    repo = Path("/work/repo")

    def test_the_vulnerable_packages_come_per_lockfile_with_version_advisories_and_the_fix(self) -> None:
        lockfiles = vuln.lockfile_rows(self.repo, fixture())
        self.assertEqual([f["lockfile"] for f in lockfiles], ["package-lock.json", "services/api/Cargo.lock"],
                         "a package with no vulnerability, and its lockfile, are left out")
        lodash, minimist = lockfiles[0]["packages"]
        self.assertEqual((lodash["name"], lodash["version"], lodash["ecosystem"], lodash["severity"],
                          lodash["fixed_in"]), ("lodash", "4.17.20", "npm", "high", "4.17.21"))
        self.assertEqual([v["ids"] for v in lodash["vulnerabilities"]], [["GHSA-35jh-r3h4-6jhm"], ["GHSA-29mw-wpgm-hmr9"]])
        self.assertEqual(lodash["vulnerabilities"][0]["aliases"], ["CVE-2021-23337"], "an alias is not the record's own id")
        self.assertEqual(lodash["vulnerabilities"][0]["summary"], "Command Injection in lodash")
        self.assertEqual((minimist["name"], minimist["severity"], minimist["fixed_in"]), ("minimist", "critical", "1.2.6"),
                         "the fix above 1.2.5, not the backport to 0.2.4")

    def test_a_group_of_records_for_one_vulnerability_is_one_vulnerability(self) -> None:
        (smallvec,) = vuln.lockfile_rows(self.repo, fixture())[1]["packages"]
        self.assertEqual(len(smallvec["vulnerabilities"]), 1)
        self.assertEqual(smallvec["vulnerabilities"][0]["ids"], ["GHSA-fhg7-m89q-25r3", "RUSTSEC-2021-0003"])
        self.assertEqual(smallvec["vulnerabilities"][0]["aliases"], ["CVE-2021-25900"])

    def test_the_counts_by_severity_are_of_distinct_vulnerabilities(self) -> None:
        counts = vuln.counts(vuln.lockfile_rows(self.repo, fixture()))
        self.assertEqual(counts, {"critical": 1, "high": 2, "medium": 1, "low": 0, "unknown": 0})

    def test_a_level_comes_from_the_score_of_the_group_else_the_label_of_the_record_else_it_is_unknown(self) -> None:
        self.assertEqual([vuln.cvss_level(s) for s in ("9.8", "9.0", "7.5", "4.0", "3.9", "0.1", "0.0", "", None, "x")],
                         ["critical", "critical", "high", "medium", "low", "low", None, None, None, None])
        rows = {"package": {"name": "p", "version": "1"},
                "vulnerabilities": [{"id": "A", "database_specific": {"severity": "MODERATE"}}, {"id": "B"}]}
        self.assertEqual([v["severity"] for v in vuln.package_row(rows)["vulnerabilities"]], ["medium", "unknown"],
                         "without groups each record stands alone")

    def test_the_fix_is_the_version_that_fixes_every_vulnerability_that_has_one(self) -> None:
        def record(name: str, fixed: str) -> dict:
            return {"id": name, "affected": [{"package": {"name": "P"}, "ranges": [{"events": [{"introduced": "0"},
                                                                                              {"fixed": fixed}]}]}]}
        row = vuln.package_row({"package": {"name": "p", "version": "1.9.0"},
                                "vulnerabilities": [record("A", "1.10.0"), record("B", "2.0.1"), record("C", "1.2")]})
        self.assertEqual(row["fixed_in"], "2.0.1")
        self.assertEqual([v["fixed"] for v in row["vulnerabilities"]], [["1.10.0"], ["2.0.1"], ["1.2"]],
                         "a fix below the version is shown only when nothing above it is known")

    def test_a_fix_named_by_a_commit_is_left_out(self) -> None:
        record = {"id": "A", "affected": [{"package": {"name": "p"}, "ranges": [
            {"type": "GIT", "events": [{"introduced": "0"}, {"fixed": "c45d7c49ea75133e52ab22a8e9e13173938e36ff"}]},
            {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.20.0"}]}]}]}
        row = vuln.package_row({"package": {"name": "p", "version": "2.19.0"}, "vulnerabilities": [record]})
        self.assertEqual((row["fixed_in"], row["vulnerabilities"][0]["fixed"]), ("2.20.0", ["2.20.0"]))

    def test_a_lockfile_given_in_two_results_is_one_row_with_each_package_once(self) -> None:
        def result(*names: str) -> dict:
            return {"source": {"path": "/work/repo/py/requirements.txt", "type": "lockfile"},
                    "packages": [{"package": {"name": n, "version": "1"}, "vulnerabilities": [{"id": f"X-{n}"}]}
                                 for n in names]}
        (row,) = vuln.lockfile_rows(self.repo, {"results": [result("requests"), result("requests", "idna")]})
        self.assertEqual((row["lockfile"], [p["name"] for p in row["packages"]]),
                         ("py/requirements.txt", ["requests", "idna"]))

    def test_a_row_names_one_id_per_vulnerability_and_three_at_most(self) -> None:
        package = {"vulnerabilities": [{"ids": [f"GHSA-{n}", f"PYSEC-{n}"]} for n in range(5)]}
        self.assertEqual(vuln.advisories(package), "GHSA-0, GHSA-1, GHSA-2 and 2 more")
        self.assertEqual(vuln.advisories({"vulnerabilities": [{"ids": ["GHSA-0", "PYSEC-0"]}]}), "GHSA-0")

    def test_nothing_to_report_is_an_empty_list(self) -> None:
        self.assertEqual(vuln.lockfile_rows(self.repo, {"results": []}), [])
        self.assertEqual(vuln.lockfile_rows(self.repo, {}), [])


class VulnerabilityCase(BroomCase):
    def setUp(self) -> None:
        super().setUp()
        self.log = self.tmp / "calls.log"
        self.repo_dir = self.repo({"pyproject.toml": PYPROJECT, "a.py": "X = 1\n"})

    def scanner(self, rc: int = 1, out: str = "", err: str = "") -> dict:
        """An environment whose osv-scanner logs where it ran and how, says `out` and `err`, and exits with `rc`."""
        body = f'echo "$(pwd -P) $*" >> {self.log}\n'
        body += f"printf '%s\\n' {json.dumps(err)} >&2\n" if err else ""
        # the fixture's paths are `/work/repo`: here they are the repo it ran in
        body += f'sed "s#/work/repo#$(pwd -P)#g" {FIXTURE}\n' if out == "fixture" else ""
        body += f"printf '%s\\n' '{out}'\n" if out and out != "fixture" else ""
        return self.fake_path(keep=("sed",), fakes={"osv-scanner": f"{body}exit {rc}"})

    def calls(self) -> list:
        """What the fake osv-scanner logged, a line per call."""
        return self.log.read_text().splitlines() if self.log.exists() else []

    def vulnerabilities(self, env: dict, *args: str) -> dict:
        done = self.cli(self.repo_dir, "diagnose", "--json", *args, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["dependencies"]["vulnerabilities"]


class FlagTest(VulnerabilityCase):
    def test_without_the_flag_osv_scanner_is_never_started_and_the_section_ends_with_one_line_about_the_flag(self) -> None:
        env = self.scanner(out="fixture")
        data = self.vulnerabilities(env)
        self.assertEqual(data, OFF)
        text = self.cli(self.repo_dir, "diagnose", env=env).stdout
        section = text.split("## Dependencies\n")[1].split("\n\n## ")[0].splitlines()
        self.assertEqual(section[-1], f"  {vuln.HINT}")
        self.assertIn("`broom diagnose --vulnerabilities`", section[-1])
        self.assertIn("sends package names and versions to api.osv.dev", section[-1])
        self.assertEqual(self.calls(), [], "never started")

    def test_no_hook_and_no_other_command_starts_it_either(self) -> None:
        env = self.scanner(out="fixture")
        self.session(self.repo_dir, "s1", env)
        self.session(self.repo_dir, "s1", env, "session-scan")
        (self.repo_dir / "a.py").write_text("X = 2\n")
        self.sh(self.repo_dir, "git", "add", "a.py")
        payload = {"session_id": "s1", "cwd": str(self.repo_dir), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "git commit -m x"}, "tool_use_id": "t1"}
        hook = subprocess.run([str(BROOM), "hook", "commit"], input=json.dumps(payload), capture_output=True,
                              text=True, env=env, cwd=self.repo_dir)
        self.assertEqual((hook.returncode, hook.stderr), (0, ""))
        for command in (["doctor"], ["smells"], ["stats"], ["diagnose", "--json"]):
            self.cli(self.repo_dir, *command, env=env)
        self.assertEqual(self.calls(), [])

    def test_with_the_flag_it_runs_on_the_repo_with_the_documented_arguments_and_its_json_is_read(self) -> None:
        data = self.vulnerabilities(self.scanner(out="fixture"), "--vulnerabilities")
        self.assertEqual(self.calls(), [f"{self.repo_dir} scan source -r {self.repo_dir} --format json"])
        self.assertEqual((data["asked"], data["status"], data["vulnerable_packages"]), (True, "ok", 3))
        self.assertEqual(data["severity"], {"critical": 1, "high": 2, "medium": 1, "low": 0, "unknown": 0})
        self.assertEqual([f["lockfile"] for f in data["lockfiles"]], ["package-lock.json", "services/api/Cargo.lock"])
        self.assertIn("api.osv.dev", data["sends"])

    def test_the_report_says_what_is_sent_where_then_lists_the_packages_per_lockfile(self) -> None:
        text = self.cli(self.repo_dir, "diagnose", "--vulnerabilities", env=self.scanner(out="fixture")).stdout
        section = text.split("## Dependencies\n")[1].split("\n\n## ")[0]
        self.assertIn("osv-scanner sends the names and versions of the packages in the lockfiles to api.osv.dev", section)
        self.assertIn("3 vulnerable package(s) in 2 lockfile(s); 1 critical, 2 high, 1 medium", section)
        self.assertRegex(section, r"\n  package-lock\.json\n    package\s+version\s+worst\s+advisories\s+fixed in\n")
        self.assertRegex(section, r"\n    lodash\s+4\.17\.20\s+high\s+GHSA-35jh-r3h4-6jhm, GHSA-29mw-wpgm-hmr9\s+4\.17\.21\n")
        self.assertRegex(section, r"\n    minimist\s+1\.2\.5\s+critical\s+GHSA-xvch-5gv4-984h\s+1\.2\.6\n")
        self.assertNotIn("are not looked up", section, "the line about the flag is for the diagnosis without it")

    def test_the_flag_without_the_tool_says_so_with_the_install_command_and_sends_nothing(self) -> None:
        data = self.vulnerabilities(self.fake_path(), "--vulnerabilities")
        self.assertEqual((data["status"], data["install"], data["lockfiles"]), ("not installed", "brew install osv-scanner", []))
        text = self.cli(self.repo_dir, "diagnose", "--vulnerabilities", env=self.fake_path()).stdout
        self.assertIn("not measured: osv-scanner is not installed (`brew install osv-scanner`)", text)


class OutcomeTest(VulnerabilityCase):
    def asked(self, env: dict) -> dict:
        return self.vulnerabilities(env, "--vulnerabilities")

    def test_nothing_known_is_said_so(self) -> None:
        data = self.asked(self.scanner(rc=0, out='{"results": []}'))
        self.assertEqual((data["status"], data["vulnerable_packages"], data["lockfiles"]), ("ok", 0, []))
        text = self.cli(self.repo_dir, "diagnose", "--vulnerabilities", env=self.scanner(rc=0, out='{"results": []}')).stdout
        self.assertIn("no known vulnerability in the packages of the lockfiles", text)

    def test_no_lockfile_found_is_not_a_failure(self) -> None:
        data = self.asked(self.scanner(rc=128, err="No package sources found"))
        self.assertEqual((data["status"], data["error"]), ("no packages", ""))
        text = self.cli(self.repo_dir, "diagnose", "--vulnerabilities", env=self.scanner(rc=128)).stdout
        self.assertIn("osv-scanner found no lockfile or manifest to check", text)

    def test_a_failure_is_said_with_its_first_error_line(self) -> None:
        data = self.asked(self.scanner(rc=127, err="Failed to run scanner: couldn't reach api.osv.dev"))
        self.assertEqual((data["status"], data["error"]), ("failed", "Failed to run scanner: couldn't reach api.osv.dev"))
        text = self.cli(self.repo_dir, "diagnose", "--vulnerabilities", env=self.scanner(rc=127, err="boom")).stdout
        self.assertIn("osv-scanner failed: boom", text)

    def test_output_that_is_not_json_is_a_failure_too(self) -> None:
        data = self.asked(self.scanner(rc=1, out="not json"))
        self.assertEqual((data["status"], data["error"]), ("failed", "not json"))

    def test_the_exit_code_of_diagnose_is_0_whatever_osv_scanner_found(self) -> None:
        for env in (self.scanner(rc=1, out="fixture"), self.scanner(rc=127, err="boom"), self.fake_path()):
            done = self.cli(self.repo_dir, "diagnose", "--vulnerabilities", env=env)
            self.assertEqual(done.returncode, 0, done.stderr)


class TimeoutTest(VulnerabilityCase):
    def test_it_gets_five_minutes_and_a_timeout_is_a_failure(self) -> None:
        self.assertEqual(RUN_SECONDS, 300)
        path = self.scanner()["PATH"]
        with mock.patch.dict(os.environ, {"PATH": path}), \
                mock.patch("broom.dependencies.run", return_value=(None, "", "")) as run:
            data = vuln.scan(self.repo_dir)
        self.assertEqual(run.call_args.kwargs["timeout"], 300)
        self.assertEqual(run.call_args.args[0][1:], ["scan", "source", "-r", str(self.repo_dir), "--format", "json"])
        self.assertEqual((data["status"], data["error"]), ("failed", "timed out after 300 s"))


class DoctorTest(VulnerabilityCase):
    def test_the_doctor_lists_it_as_optional_in_any_repo_with_code_and_it_changes_nothing_else(self) -> None:
        bare = json.loads(self.cli(self.repo_dir, "doctor", "--json", env=self.fake_path()).stdout)
        tool = next(t for t in bare["optional"] if t["tool"] == "osv-scanner")
        self.assertEqual((tool["installed"], tool["install"]), (False, "brew install osv-scanner"))
        self.assertIn("--vulnerabilities", tool["for"])
        mine = json.loads(self.cli(self.repo_dir, "doctor", "--json", env=self.scanner(rc=0)).stdout)
        self.assertTrue(next(t for t in mine["optional"] if t["tool"] == "osv-scanner")["installed"])
        for key in ("items", "fix", "configure", "healthy"):
            self.assertEqual(bare[key], mine[key])
        self.assertEqual(self.calls(), [], "listing it never starts it")
