"""Independent analytic regression cases for the November calc2 audit."""
import json
import os
import shutil
import subprocess

from django.conf import settings
from django.test import SimpleTestCase, tag


@tag('calc2')
class AuditMathTest(SimpleTestCase):
    def test_analytic_counterexamples(self):
        node = shutil.which('node')
        if not node:
            if os.environ.get('CI'):
                self.fail('Node is required for the calc2 audit regressions in CI.')
            self.skipTest('Node is unavailable; calc2 audit regressions did not run.')
        env = dict(os.environ)
        env.pop('RESULT_JSON', None)
        result = subprocess.run(
            [node, 'calc2/tests/astra_audit_fixes.mjs'],
            cwd=settings.BASE_DIR, env=env, capture_output=True,
            text=True, encoding='utf-8', timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(result.stdout)
        self.assertGreaterEqual(summary['total'], 128)
        self.assertEqual(summary['passed'], summary['total'])
        self.assertEqual(summary['failures'], [])
