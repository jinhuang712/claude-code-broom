"""Whether a Bash command runs tests, judged by its words (testcmd), and what .broom.json `test_commands` adds."""

from __future__ import annotations

import unittest

from support import BroomCase

from broom import doctor
from broom.testcmd import is_test_run

RUNNERS = (
    "pytest", "pytest -q tests/test_a.py", "python3 -m pytest", "python -m unittest discover -s tests", "tox -e py39",
    "nox -s tests", "go test ./...", "cargo test", "cargo nextest run", "swift test", "npm test", "npm run test",
    "npm run test:unit", "pnpm test", "yarn test", "bun test", "jest", "npx vitest run", "mocha --recursive",
    "make test", "xcodebuild -scheme App test", "python3 tests/run.py", "bash run_tests.sh", "sh test.sh",
    "cd sub && pytest -x", "CI=1 time uv run pytest", "bash -c 'cd x && npm test'", ".venv/bin/pytest",
)
NO_RUNNERS = (
    "ls tests/", 'git commit -m "run pytest"', "echo npm test", "ls -la", "cat tests/run.py", "grep -r pytest .",
    "pip install pytest", "npm install", "npm run build", "go build ./...", "make build", "python3 tests/helper.py",
    "python3 -c 'import pytest'", "git commit -m x <<'EOF'\npytest\nEOF",
)


class RecognizerTest(BroomCase):
    def test_each_runner_is_seen_by_its_own_words(self) -> None:
        for command in RUNNERS:
            self.assertTrue(is_test_run(command), command)

    def test_commands_that_only_look_like_a_test_run_are_none(self) -> None:
        for command in NO_RUNNERS:
            self.assertFalse(is_test_run(command), command)

    def test_a_part_of_a_longer_command_counts_and_a_word_in_quotes_does_not(self) -> None:
        self.assertTrue(is_test_run("cd x && pytest | tail -5"))
        self.assertTrue(is_test_run("make build; npm test"))
        self.assertFalse(is_test_run('echo "&& pytest"'))
        self.assertFalse(is_test_run("echo 'it ran' ; git status"))

    def test_a_command_the_shell_cant_follow_is_read_as_words(self) -> None:
        self.assertTrue(is_test_run("echo 'oops; pytest"), "an open quote: the words are read as they stand")

    def test_the_repos_own_test_commands_count_by_the_words_they_start_with(self) -> None:
        custom = ["just check", "bazel test"]
        for command in ("just check", "just check --all", "bazel test //...", "time just check", "cd x && just check"):
            self.assertTrue(is_test_run(command, custom), command)
        for command in ("just build", "echo just check", "bazel build //..."):
            self.assertFalse(is_test_run(command, custom), command)
        self.assertFalse(is_test_run("just check"), "no repo named it")
        self.assertFalse(is_test_run("just check", "just check"), "not a list: no test commands")

    def test_doctor_checks_test_commands_and_knows_the_rules_name(self) -> None:
        for text, status in (('{"test_commands": ["just check"]}', "ok"), ('{"test_commands": "just check"}', "broken"),
                             ('{"test_commands": ["just check", 3]}', "broken"), ('{"test_commands": [""]}', "broken"),
                             ('{"smells_off": ["tests_not_run"]}', "ok"), ('{"smells_off": ["tests_ran"]}', "broken")):
            r = self.repo({".broom.json": text, "a.py": "x = 1\n"})
            (item,) = doctor.check_repo_file(r)
            self.assertEqual(item.status, status, f"{text}: {item.detail}")
        r = self.repo({".broom.json": '{"test_commands": ["just check", "bazel test"]}'})
        self.assertIn("2 test command(s)", doctor.check_repo_file(r)[0].detail)


if __name__ == "__main__":
    unittest.main()
