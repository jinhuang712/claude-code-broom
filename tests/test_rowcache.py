"""A file's content is measured once, however often it is checked."""

from __future__ import annotations

import unittest
from unittest import mock

from support import HAS_PY, BroomCase, py_function

from broom import rowcache
from broom.measure import Raw
from broom.rowcache import RowCache
from broom.smells import find_smells

LIMITS = {"function_lines": (50, 100), "params": (5, 8)}


class RowCacheTests(BroomCase):
    def setUp(self) -> None:
        super().setUp()
        self.calls: list = []

    def measuring(self, notes_to_add=()):
        def measure(_root, texts, _limits, _repo, notes):
            self.calls.append(sorted(texts))
            notes += list(notes_to_add)
            return [Raw(rel, 1, "function_lines", "f", len(text), "fake") for rel, text in texts.items()]

        return measure

    def cache(self, limits=LIMITS, **kw) -> RowCache:
        return RowCache(self.tmp, limits, self.measuring(**kw))

    def test_content_measured_before_is_not_measured_again(self) -> None:
        first = self.cache()
        rows = first.measure(self.tmp, {"a.py": "aa", "b.py": "bbb"}, [])
        first.save()
        again = self.cache()
        self.assertEqual(again.measure(self.tmp, {"a.py": "aa", "b.py": "bbb"}, []), rows)
        self.assertEqual(self.calls, [["a.py", "b.py"]], "the second time nothing was measured")

    def test_only_the_file_that_changed_is_measured_again(self) -> None:
        first = self.cache()
        first.measure(self.tmp, {"a.py": "aa", "b.py": "bbb"}, [])
        first.save()
        rows = self.cache().measure(self.tmp, {"a.py": "aa", "b.py": "changed"}, [])
        self.assertEqual(self.calls[-1], ["b.py"])
        self.assertEqual(sorted((r.rel, r.value) for r in rows), [("a.py", 2), ("b.py", 7)])

    def test_another_limit_or_path_is_another_measurement(self) -> None:
        first = self.cache()
        first.measure(self.tmp, {"a.py": "aa"}, [])
        first.save()
        self.cache({"function_lines": (10, 20)}).measure(self.tmp, {"a.py": "aa"}, [])
        self.cache().measure(self.tmp, {"c.py": "aa"}, [])
        self.assertEqual(self.calls, [["a.py"], ["a.py"], ["c.py"]])

    def test_a_tool_that_went_missing_gets_its_files_measured_again(self) -> None:
        first = self.cache()
        first.measure(self.tmp, {"a.py": "aa"}, [])
        first.save()
        with mock.patch("broom.rowcache.resolve_bin", return_value=None):
            self.cache().measure(self.tmp, {"a.py": "aa"}, [])
        self.assertEqual(self.calls, [["a.py"], ["a.py"]], "so the missing tool is said so, not hidden by old rows")

    def test_a_measurement_that_did_not_finish_is_not_kept(self) -> None:
        notes: list = []
        part = self.cache(notes_to_add=["timeout:ruff measuring smells"])
        part.measure(self.tmp, {"a.py": "aa"}, notes)
        part.save()
        self.assertEqual(notes, ["timeout:ruff measuring smells"], "the caller still hears of it")
        self.cache().measure(self.tmp, {"a.py": "aa"}, [])
        self.assertEqual(self.calls, [["a.py"], ["a.py"]])

    @unittest.skipUnless(HAS_PY, "ruff")
    def test_a_second_check_of_the_same_change_measures_nothing(self) -> None:
        long_one = py_function("long_function", 70)
        r = self.repo({"m.py": "x = 1\n"})
        (r / "m.py").write_text(long_one)
        with mock.patch("broom.rowcache.measure", wraps=rowcache.measure) as spy:
            first, _ = find_smells(r, [r / "m.py"], "HEAD")
            measured_first = spy.call_count
            second, _ = find_smells(r, [r / "m.py"], "HEAD")
        self.assertGreater(measured_first, 0)
        self.assertEqual(spy.call_count, measured_first, "the same content, measured once")
        self.assertEqual([(s.metric, s.line) for s in second], [(s.metric, s.line) for s in first])
        self.assertTrue(first, "the long function is still found from the cache")


if __name__ == "__main__":
    unittest.main()
