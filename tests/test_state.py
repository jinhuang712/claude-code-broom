"""Hooks that run at once, and the state files they share."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from support import ROOT, BroomCase

from broom import gate
from broom.gate import save_commits
from broom.state import load_json, update_json

WORKER = """
import sys
sys.path.insert(0, {lib!r})
from pathlib import Path
from broom.state import update_json
def bump(data):
    data["n"] = data.get("n", 0) + 1
    data[sys.argv[2]] = True
for _ in range(40):
    update_json(Path(sys.argv[1]), {{}}, bump)
"""


class StateTests(BroomCase):
    def test_hooks_changing_a_file_at_once_lose_nothing(self) -> None:
        path = self.tmp / "shared.json"
        script = WORKER.format(lib=str(ROOT / "lib"))
        workers = [subprocess.Popen([sys.executable, "-I", "-c", script, str(path), f"w{i}"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(6)]
        errors = [w.communicate()[1] for w in workers]
        self.assertEqual(errors, [""] * 6)
        data = json.loads(path.read_text())
        self.assertEqual(data["n"], 240, "every one of the 6 x 40 changes is in")
        self.assertTrue(all(data.get(f"w{i}") for i in range(6)))

    def test_a_file_that_is_missing_or_broken_starts_over(self) -> None:
        path = self.tmp / "new.json"
        update_json(path, {}, lambda d: d.update(a=1))
        self.assertEqual(load_json(path, None), {"a": 1})
        path.write_text("{not json")
        update_json(path, {}, lambda d: d.update(b=2))
        self.assertEqual(load_json(path, None), {"b": 2})

    def test_a_change_can_return_a_new_value(self) -> None:
        path = self.tmp / "list.json"
        update_json(path, [], lambda items: items + ["x"])
        update_json(path, [], lambda items: sorted(items + ["a"]))
        self.assertEqual(load_json(path, None), ["a", "x"])

    def test_saving_one_repos_commit_state_leaves_the_others_as_they_are(self) -> None:
        path = self.tmp / "commits.json"
        # Another hook wrote /c after this run read the file; this run knows of /a and /b, and /b is settled.
        path.write_text(json.dumps({"/a": {"pending": {"k": 1}}, "/b": {"pending": {"j": 1}},
                                    "/c": {"pending": {"z": 1}}}))
        with mock.patch.object(gate, "COMMITS", path):
            save_commits({"/a": {"pending": {"k": 2}}}, [Path("/a"), Path("/b")])
        self.assertEqual(load_json(path, None), {"/a": {"pending": {"k": 2}}, "/c": {"pending": {"z": 1}}})


if __name__ == "__main__":
    unittest.main()
