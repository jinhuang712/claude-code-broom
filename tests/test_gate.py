"""What stops a commit and how it gets through: fixing, retrying, accepting, and git's own pre-commit hook."""

from __future__ import annotations

from support import BroomCase, py_function


class GateTest(BroomCase):
    def test_accepting_can_be_turned_off(self) -> None:
        r = self.repo({"a.py": "x = 1\n"})
        (r / "a.py").write_text(py_function("huge", 120))
        self.sh(r, "git", "add", "a.py")
        self.env["BROOM_NO_ACCEPT"] = "1"
        reason = self.denied(self.commit(r, "git commit -m x"))
        self.assertIn("accepting them is off here", reason)
        self.assertNotIn("broom known --accept", reason, "Claude isn't told to do what it can't")
        out = self.cli(r, "known", "--accept", "legacy code")
        self.assertEqual(out.returncode, 1)
        self.assertIn("BROOM_NO_ACCEPT is set", out.stderr)
        self.env["BROOM_NO_ACCEPT"] = "0"
        self.assertIn("accepted", self.cli(r, "known", "--accept", "legacy code").stdout, "0 leaves it on")
