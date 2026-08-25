# -*- coding: utf-8 -*-
"""Тесты разбора текстового вывода manage.py test (scripts/output_summary.py).

Запуск:
    venv313/Scripts/python.exe -m unittest discover -s scripts/tests -t .
"""
import unittest

from scripts.output_summary import parse_summary, extract_failure_blocks

SAMPLE_OK = """Creating test database for alias 'default'...
System check identified no issues (0 silenced).
test_a (calc2.tests.x.T.test_a) ... ok
test_b (calc2.tests.x.T.test_b) ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.123s

OK
Destroying test database for alias 'default'...
"""

SAMPLE_OK_WITH_SKIPPED = """test_a (calc2.tests.x.T.test_a) ... ok
test_b (calc2.tests.x.T.test_b) ... skipped 'нет модели BGE-M3'

----------------------------------------------------------------------
Ran 2 tests in 0.050s

OK (skipped=1)
"""

SAMPLE_FAILED = """Creating test database for alias 'default'...
test_a (calc2.tests.x.T.test_a) ... ok
test_b (calc2.tests.x.T.test_b) ... FAIL
test_c (calc2.tests.x.T.test_c) ... ERROR

======================================================================
FAIL: test_b (calc2.tests.x.T.test_b)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "calc2/tests/x.py", line 10, in test_b
    self.assertEqual(1, 2)
AssertionError: 1 != 2

======================================================================
ERROR: test_c (calc2.tests.x.T.test_c)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "calc2/tests/x.py", line 20, in test_c
    raise ValueError('boom')
ValueError: boom

----------------------------------------------------------------------
Ran 3 tests in 0.456s

FAILED (failures=1, errors=1)
Destroying test database for alias 'default'...
"""

SAMPLE_TRUNCATED = """Creating test database for alias 'default'...
test_a (calc2.tests.x.T.test_a) ... ok
"""


class ParseSummaryTests(unittest.TestCase):

    def test_ok_run(self):
        summary = parse_summary(SAMPLE_OK)
        self.assertEqual(summary.ran, 2)
        self.assertEqual(summary.failures, 0)
        self.assertEqual(summary.errors, 0)
        self.assertEqual(summary.skipped, 0)
        self.assertTrue(summary.ok)
        self.assertAlmostEqual(summary.seconds, 0.123)

    def test_ok_run_with_skipped(self):
        summary = parse_summary(SAMPLE_OK_WITH_SKIPPED)
        self.assertEqual(summary.ran, 2)
        self.assertEqual(summary.skipped, 1)
        self.assertTrue(summary.ok)

    def test_failed_run_counts(self):
        summary = parse_summary(SAMPLE_FAILED)
        self.assertEqual(summary.ran, 3)
        self.assertEqual(summary.failures, 1)
        self.assertEqual(summary.errors, 1)
        self.assertEqual(summary.skipped, 0)
        self.assertFalse(summary.ok)

    def test_truncated_output_is_not_ok(self):
        summary = parse_summary(SAMPLE_TRUNCATED)
        self.assertFalse(summary.ok)
        self.assertIsNone(summary.ran)


class ExtractFailureBlocksTests(unittest.TestCase):

    def test_ok_run_has_no_blocks(self):
        self.assertEqual(extract_failure_blocks(SAMPLE_OK), [])

    def test_failed_run_has_two_full_blocks(self):
        blocks = extract_failure_blocks(SAMPLE_FAILED)
        self.assertEqual(len(blocks), 2)
        self.assertTrue(blocks[0].startswith('FAIL: test_b'))
        self.assertIn('AssertionError: 1 != 2', blocks[0])
        self.assertTrue(blocks[1].startswith('ERROR: test_c'))
        self.assertIn("ValueError: boom", blocks[1])

    def test_blocks_do_not_leak_the_trailing_summary(self):
        blocks = extract_failure_blocks(SAMPLE_FAILED)
        for block in blocks:
            self.assertNotIn('Ran 3 tests', block)
            self.assertNotIn('FAILED (failures=', block)

    def test_traceback_is_not_truncated(self):
        # многострочный traceback обязан прийти целиком, без обрезки
        block = extract_failure_blocks(SAMPLE_FAILED)[0]
        self.assertIn('Traceback (most recent call last):', block)
        self.assertIn('File "calc2/tests/x.py", line 10, in test_b', block)
        self.assertIn('self.assertEqual(1, 2)', block)


if __name__ == '__main__':
    unittest.main()
