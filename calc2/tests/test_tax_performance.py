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
    def test_number_format_cost(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the number performance probe")
        result = subprocess.run(
            [node, "calc2/tests/number_perf_probe.mjs"], cwd=settings.BASE_DIR,
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_tax_motion_lifecycle(self):
        self._run_motion_probe()

    def test_tax_motion_manifest_paths(self):
        self._run_motion_probe("--manifest-paths")

    def test_input_snap_and_tablet_results(self):
        """The omitted tablet strip, exact edits, MC and one undo per gesture."""
        node = shutil.which("node")
        self.assertIsNotNone(node)
        with tempfile.TemporaryDirectory(prefix="calc2-input-snap-") as out:
            result = subprocess.run(
                [node, "calc2/tests/input_snap_probe.mjs", "--out", out],
                cwd=settings.BASE_DIR,
                env=dict(os.environ, CALC2_BASE_URL=self.live_server_url),
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rate_label_during_held_gesture(self):
        """A held rate stays short in both controls, regardless of exact-cache state."""
        node = shutil.which("node")
        self.assertIsNotNone(node)
        with tempfile.TemporaryDirectory(prefix="calc2-rate-label-") as out:
            result = subprocess.run(
                [node, "calc2/tests/rate_label_probe.mjs", "--out", out],
                cwd=settings.BASE_DIR,
                env=dict(os.environ, CALC2_BASE_URL=self.live_server_url),
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_model_controls(self):
        """Shared live rendering preserves computed values in every scene."""
        self._run_controls_probe("controls_motion_probe.mjs")
        self._run_controls_probe("controls_motion_probe.mjs", "--parameters")
        self._run_controls_probe("controls_motion_probe.mjs", "--extras")

    def test_other_graph_handles(self):
        """Real input, held pause, one history entry and certified affine math."""
        self._run_controls_probe("controls_gesture_probe.mjs")

    def test_plants_range_does_not_run_away(self):
        """Stable slider domain and visible TC sampling, including large manual Q."""
        self._run_controls_probe("plants_range_probe.mjs")

    def _run_controls_probe(self, script, *args):
        node = shutil.which("node")
        self.assertIsNotNone(node)
        with tempfile.TemporaryDirectory(prefix="calc2-controls-") as out:
            result = subprocess.run(
                [node, "calc2/tests/" + script, "--out", out, *args],
                cwd=settings.BASE_DIR,
                env=dict(os.environ, CALC2_BASE_URL=self.live_server_url),
                capture_output=True, text=True, encoding="utf-8", timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _run_motion_probe(self, *args):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the native tax gesture probe")
        with tempfile.TemporaryDirectory(prefix="calc2-tax-motion-") as out:
            result = subprocess.run(
                [node, "calc2/tests/tax_motion_probe.mjs", "--out", out, *args],
                cwd=settings.BASE_DIR,
                env=dict(os.environ, CALC2_BASE_URL=self.live_server_url),
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
