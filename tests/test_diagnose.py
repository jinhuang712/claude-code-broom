"""broom diagnose: the whole repo as data and as a report, on throwaway repos with no linter and no jscpd on the PATH
so that what is found is the same on every machine: the shape of the JSON, the order of the report's headings, the
tools said to be missing, `--out`, a path that narrows, the exit code outside a repo and a repo of over 5,000 files."""

from __future__ import annotations

import json
import re
from pathlib import Path

from gitwork import GitWork
from support import py_function

LONG = py_function("huge", 120)  # one smell past the hard limit
BUSY = py_function("busy", 60).replace("+=", "-=")  # one hint
TS_BIG = "".join(f"export const v{i} = {i};\n" for i in range(450))  # a file over 400 lines: one hint
HEADINGS = ["Summary", "Smells by kind", "Smells by language", "Hotspots by churn", "The worst smells", "Check-up",
            "Duplicate tests", "Dependencies", "Size (code lines)", "Tests", "Rot"]


class DiagnoseTest(GitWork):
    def setUp(self) -> None:
        super().setUp()
        self.bare = self.fake_path()

    def smelly_repo(self) -> Path:
        return self.history_repo([(2000, {"a.py": LONG, "src/big.ts": TS_BIG}), (12, {"b.py": BUSY})]
                                 + [(10 - i, {"b.py": BUSY + f"\n\nB = {i}\n"}) for i in range(6)])

    def diagnose(self, r: Path, *args: str) -> dict:
        done = self.cli(r, "diagnose", "--json", *args, env=self.bare)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_the_json_holds_every_section_and_every_smell(self) -> None:
        r = self.smelly_repo()
        d = self.diagnose(r, "--top", "1")
        self.assertEqual(set(d), {"repo", "paths", "summary", "by_smell", "by_language", "by", "hotspots", "smells",
                                  "missing_tools", "notes", "stats", "checkup", "duplicate_tests", "dependencies"})
        self.assertEqual((d["repo"], d["paths"]), (str(r), []))
        s = d["summary"]
        self.assertEqual((s["files"], s["smells"], s["severe"], s["hints"]), (3, 3, 1, 2))
        self.assertGreater(s["lines"], 600)
        self.assertEqual(len(d["smells"]), 3, "every smell, whatever --top says")
        self.assertEqual(len(d["hotspots"]), 1, "the lists that --top cuts")
        self.assertEqual(d["stats"]["files"], 3)
        self.assertEqual(set(d["stats"]), {"repo", "paths", "files", "last_commits", "size", "tests", "rot", "history"})

    def test_smells_by_kind_and_by_language_with_the_worst_of_each(self) -> None:
        d = self.diagnose(self.smelly_repo())
        kinds = {k["smell"]: k for k in d["by_smell"]}
        self.assertEqual((kinds["function_lines"]["count"], kinds["function_lines"]["severe"]), (2, 1))
        self.assertEqual((kinds["file_lines"]["count"], kinds["file_lines"]["severe"]), (1, 0))
        worst = kinds["function_lines"]["worst"]
        self.assertEqual((worst["file"], worst["level"]), ("a.py", "block"))
        self.assertEqual(d["by_smell"][0]["smell"], "function_lines", "the kind with most past the hard limit first")
        self.assertEqual(d["by_language"], [{"language": "py", "count": 2, "severe": 1, "hints": 1},
                                            {"language": "js", "count": 1, "severe": 0, "hints": 1}])

    def test_hotspots_come_by_churn_and_every_smell_has_no_was(self) -> None:
        d = self.diagnose(self.smelly_repo())
        self.assertEqual(d["by"], "churn")
        busy = next(f for f in d["hotspots"] if f["file"] == "b.py")
        self.assertEqual((busy["changes"], busy["score"]), (7, (3 * busy["severe"] + busy["hints"]) * 8))
        self.assertEqual(d["hotspots"][0]["file"], "b.py", "a hint changed seven times outranks a severe smell changed once")
        self.assertEqual({s["was"] for s in d["smells"]}, {None})

    def test_commits_moves_the_churn_window_and_the_history(self) -> None:
        d = self.diagnose(self.smelly_repo(), "--commits", "2")
        self.assertEqual((d["stats"]["last_commits"], d["stats"]["history"]["last_commits"]), (2, 2))
        self.assertEqual({f["file"]: f["changes"] for f in d["hotspots"]}["b.py"], 2, "only the last two commits")
        self.assertEqual(self.diagnose(self.smelly_repo())["stats"]["last_commits"], 500)

    def test_the_tools_that_were_missing_are_named_in_the_data_and_the_report(self) -> None:
        r = self.smelly_repo()
        d = self.diagnose(r)
        self.assertEqual(sorted(t.split(" ")[0] for t in d["missing_tools"]), ["ast-grep", "jscpd", "oxlint", "ruff"])
        text = self.cli(r, "diagnose", env=self.bare).stdout
        self.assertIn("these tools were missing", text)
        self.assertIn("ruff (brew install ruff)", text)

    def test_the_report_reads_as_markdown_in_the_order_of_its_headings(self) -> None:
        r = self.smelly_repo()
        done = self.cli(r, "diagnose", "--top", "2", env=self.bare)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertTrue(lines[0].startswith("# broom diagnose: "), lines[0])
        titles = [line[3:] for line in lines if line.startswith("## ")]
        self.assertEqual([re.sub(r"\(\d+ of the last .*", "", t).strip() if t.startswith("History") else t for t in titles],
                         [*HEADINGS, "History"])
        self.assertRegex(lines[-1], r"^broom diagnose took \d+(\.\d)? s$")
        self.assertIn("... and 1 more; `broom smells --top 3` lists them all, `--only KIND` one kind", done.stdout,
                      "the worst smells are cut at --top, and the rest is one command away, with no JSON to read")
        self.assertNotIn("\x1b[", done.stdout, "no colour")

    def test_the_summary_comes_first_with_its_counts(self) -> None:
        text = self.cli(self.smelly_repo(), "diagnose", env=self.bare).stdout
        summary = text.split("## Smells by kind")[0]
        self.assertRegex(summary, r"files read\s+3\n")
        self.assertRegex(summary, r"past the hard limit\s+1\n")
        self.assertRegex(summary, r"hints\s+2\n")

    def test_out_writes_the_report_or_the_json_and_says_where(self) -> None:
        r = self.smelly_repo()
        text_file, json_file = self.tmp / "d.md", self.tmp / "d.json"
        done = self.cli(r, "diagnose", "--out", str(text_file), env=self.bare)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.count("\n"), 1)
        self.assertIn(str(text_file), done.stdout)
        self.assertTrue(text_file.read_text().startswith("# broom diagnose: "))
        done = self.cli(r, "diagnose", "--json", "--out", str(json_file), env=self.bare)
        self.assertEqual(done.stdout.count("\n"), 1)
        self.assertEqual(json.loads(json_file.read_text())["summary"]["smells"], 3)
        bad = self.cli(r, "diagnose", "--out", str(self.tmp / "no" / "such" / "d.md"), env=self.bare)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("can't write", bad.stderr)

    def test_a_path_narrows_the_diagnosis(self) -> None:
        d = self.diagnose(self.smelly_repo(), "a.py")
        self.assertEqual((d["paths"], d["summary"]["files"], d["summary"]["smells"]), (["a.py"], 1, 1))
        self.assertEqual({s["file"] for s in d["smells"]}, {"a.py"})

    def test_outside_a_git_repo_it_exits_1(self) -> None:
        plain = self.tmp / "plain"
        plain.mkdir()
        done = self.cli(plain, "diagnose", env=self.bare)
        self.assertEqual(done.returncode, 1)
        self.assertIn("not inside a git repository", done.stderr)

    def test_a_repo_with_no_code_still_reports(self) -> None:
        d = self.diagnose(self.repo({"README.md": "hello\n"}))
        self.assertEqual((d["summary"]["files"], d["summary"]["smells"], d["by_smell"], d["hotspots"]), (0, 0, [], []))
        text = self.cli(self.repo({"README.md": "hello\n"}), "diagnose", env=self.bare).stdout
        self.assertIn("## Smells by kind\n  none", text)

    def test_a_repo_of_over_5000_files_is_read_in_full(self) -> None:
        files = {f"pkg/m{i}.py": f"X{i} = {i}\n" for i in range(5100)}
        files["pkg/huge.py"] = LONG
        d = self.diagnose(self.repo(files), "--top", "3")
        self.assertEqual((d["summary"]["files"], d["summary"]["severe"]), (5101, 1), "no limit on the files read")
        self.assertEqual(d["smells"][0]["file"], "pkg/huge.py")
