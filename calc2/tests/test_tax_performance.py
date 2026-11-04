"""Tax input must not redraw the model to animate labels or move the axes."""
import os
import shutil
import subprocess
import tempfile

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag


# A live HTTP server and browser must run alone, as the other calc2 probes do.
@tag("calc2", "browser", "serial")
class TaxPerformanceTest(StaticLiveServerTestCase):
    def test_tax_frames_and_coordinates(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the tax regression probe")
        with tempfile.TemporaryDirectory(prefix="calc2-tax-perf-") as out:
            result = subprocess.run(
                [node, "calc2/tests/tax_perf_probe.mjs", "--out", out],
                cwd=settings.BASE_DIR,
                env=dict(os.environ, CALC2_BASE_URL=self.live_server_url),
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_number_notation(self):
        """Existing independent radical/fraction/non-radical cases guard PSLQ."""
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the exact-number probe")
        result = subprocess.run(
            [node, "calc2/tests/astra_numbers_probe.mjs"], cwd=settings.BASE_DIR,
            env=dict(os.environ, CALC2_BASE_URL=self.live_server_url),
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
