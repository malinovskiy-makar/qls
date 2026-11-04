"""Reproduce the unrelated raw-HTML '73' assertion on untouched A2.

Only the synthetic database sequence is chosen to reproduce the ID seen in
the complete run. The original test body and application are unmodified.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from claude.calc2_astra_20261102.run_final_ci import PYTHON, environment

BASE = Path('/private/tmp/calc2-astra-runtime-20261102/final-ci/baseline-a2')
CODE = '''
import django
django.setup()
from django.db import connection
from django.test.runner import DiscoverRunner
from catalog.tests.test_catalog_redesign import ScoreTests
original_setup = ScoreTests.setUpTestData
def chosen_id(cls):
    with connection.cursor() as cursor:
        cursor.execute("SELECT setval(pg_get_serial_sequence('problems_problem', 'id'), 11673, false)")
    original_setup()
ScoreTests.setUpTestData = classmethod(chosen_id)
failures = DiscoverRunner(verbosity=2, interactive=False).run_tests([
    'catalog.tests.test_catalog_redesign.ScoreTests.test_процента_нет_и_при_поиске'])
print('EXPECTED_BASELINE_FAILURE_REPRODUCED=' + str(failures == 1))
raise SystemExit(0 if failures == 1 else 1)
'''

if __name__ == '__main__':
    if (BASE / '.env').exists():
        raise SystemExit('Unexpected .env')
    env = environment()
    env['TEST_DATABASE_NAME'] = 'test_calc2_score_a2'
    raise SystemExit(subprocess.call([PYTHON, '-c', CODE], cwd=BASE, env=env))
