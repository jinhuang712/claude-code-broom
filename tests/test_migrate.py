"""The first time broom makes a repo's folder, that repo's records move out of the data directory's old shared files,
and another repo's stay there until broom works in it."""

from __future__ import annotations

import json
import unittest

from test_repodata import RepoDataCase

from broom import migrate


class MigrationTest(RepoDataCase):
    def test_one_repos_records_move_and_anothers_stay(self) -> None:
        mine, other = self.repo({"a.py": "x = 1\n"}), self.repo({"a.py": "x = 1\n"})
        rows = [{"v": "0.31.0", "t": n, "repo": str(repo), "event": "block", "key": f"k{n}", "tool": "ruff",
                 "rule": "F401", "file": "a.py"} for n, repo in enumerate([mine, other, mine])]
        data = self.tmp / "data"
        data.mkdir(exist_ok=True)
        (data / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        entry = {"t": 1, "line": 1, "tool": "ruff", "rule": "F401", "msg": "m"}
        (data / "baseline.json").write_text(json.dumps({"km": {**entry, "file": str(mine / "a.py")},
                                                        "ko": {**entry, "file": str(other / "a.py")}}))
        (data / "commits.json").write_text(json.dumps({str(mine): {"pending": {}}, str(other): {"pending": {}}}))
        self.assertEqual(self.cli(mine, "known").returncode, 0)
        moved = [json.loads(x) for x in (mine / ".broom" / "ledger.jsonl").read_text().splitlines()]
        self.assertEqual([(x["key"], x["v"]) for x in moved], [("k0", "0.31.0"), ("k2", "0.31.0")], "in order")
        self.assertEqual([json.loads(x)["key"] for x in (data / "ledger.jsonl").read_text().splitlines()], ["k1"])
        self.assertEqual(list(json.loads((mine / ".broom" / "baseline.json").read_text())), ["km"])
        self.assertEqual(json.loads((mine / ".broom" / "baseline.json").read_text())["km"]["file"], "a.py")
        self.assertEqual(list(json.loads((data / "baseline.json").read_text())), ["ko"])
        self.assertEqual(list(json.loads((data / "commits.json").read_text())), [str(other)])
        self.assertTrue(migrate.waiting(), "the other repo's records wait for it")
        self.assertEqual(self.cli(other, "known").returncode, 0)
        self.assertFalse(migrate.waiting(), "nothing is left once both moved")


if __name__ == "__main__":
    unittest.main()
