"""Повтор красных классов CI на неизменённом A2, с отдельной тестовой БД."""
import json
from pathlib import Path
import subprocess
import sys
import time

from run_final_ci import LOGS, PYTHON, ROOT, environment

BASELINE = Path('/private/tmp/calc2-astra-runtime-20261102/final-ci/baseline-a2')
LABELS = [
    'problems.tests.test_corpus_diagnostics.ShadowFingerprintTests',
    'problems.tests.test_embedding_formula.V1ByteForByteTests',
    'problems.tests.test_embeddings_transfer',
    'problems.tests.test_exams.ExamCreationTests',
    'problems.tests.test_obzor_build.FiltersRowTests',
    'problems.tests.test_review55.CatalogFocusRingTests',
    'problems.tests.test_work_settings.ManualSearchFiltersStayComplete',
    'vp.tests.test_take.FinishTests',
    'problems.tests.test_typography.EmDashTests',
    'calc2.tests.test_calc2_previews',
    'catalog.tests.test_attempt_api.AttemptApiTests',
    'catalog.tests.test_no_slop.NoAiKeyProblemPageTests',
    'config.tests.test_site_env.SiteEnvDefaultTests',
]


def main():
    if not (BASELINE / 'manage.py').is_file() or (BASELINE / '.env').exists():
        raise SystemExit('Нужен чистый архив A2 без .env.')
    env = environment()
    env['TEST_DATABASE_NAME'] = 'test_calc2_a2_proof'
    if len(sys.argv) > 1 and sys.argv[1] == 'canon':
        import shutil
        env['CALC2_BASE_URL'] = 'http://127.0.0.1:8114'
        log = LOGS / 'baseline-canon.log'
        with log.open('w') as output:
            code = subprocess.call([shutil.which('node', path=env['PATH']),
                                    'calc2/tests/canon_checks.mjs'], cwd=ROOT, env=env,
                                   stdout=output, stderr=subprocess.STDOUT)
        if code == 0:
            findings = json.loads(log.read_text().split('###CANON-JSON###')[-1])
            print(json.dumps({k: v for k, v in findings.items() if v['n']}))
            code = int(any(v['n'] for v in findings.values()))
        return code
    if len(sys.argv) > 1 and sys.argv[1] == 'serve':
        import socket
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 8114))
        env.update(ALLOWED_HOSTS='127.0.0.1,localhost', SITE_ENV='dev')
        return subprocess.call([PYTHON, 'manage.py', 'runserver', '127.0.0.1:8114',
                                '--noreload', '--insecure', '--settings=config.settings_test_pg'],
                               cwd=BASELINE, env=env)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    log = LOGS / f'baseline-{stamp}.log'
    command = [PYTHON, 'manage.py', 'test', *LABELS, '--settings=config.settings_test_pg', '--verbosity', '2', '--noinput']
    start = time.monotonic()
    with log.open('w') as output:
        code = subprocess.call(command, cwd=BASELINE, env=env, stdout=output, stderr=subprocess.STDOUT)
    row = {'base': '4e87a8db02647f297d5cf1a1eb776e62928071cd', 'command': command[1:],
           'code': code, 'seconds': round(time.monotonic() - start, 1), 'log': str(log)}
    (LOGS / f'baseline-{stamp}.json').write_text(json.dumps(row, indent=2) + '\n')
    print(json.dumps(row), flush=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
