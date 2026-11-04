"""History grouping depends on input times, not delayed rendering."""
import json
import os
import shutil
import subprocess

from django.conf import settings
from django.test import SimpleTestCase, tag


@tag('calc2')
class SessionTimingTest(SimpleTestCase):
    def test_delayed_history_commit_preserves_input_groups(self):
        node = shutil.which('node')
        if not node:
            if os.environ.get('CI'):
                self.fail('Node is required for calc2 history regressions in CI.')
            self.skipTest('Node is unavailable; history regressions did not run.')
        result = subprocess.run(
            [node, 'calc2/tests/session_timing.mjs'], cwd=settings.BASE_DIR,
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary['total'], 16)
        self.assertEqual(summary['passed'], 16)
        self.assertEqual(summary['failures'], [])
