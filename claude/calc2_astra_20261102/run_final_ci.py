"""Five CI groups on isolated synthetic services; never reads a real .env."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path('/private/tmp/calc2-astra-runtime-20261102')
LOGS = ROOT / '.calc2-astra-local/logs/final-ci'
PYTHON = str(RUNTIME / 'venv313/bin/python')


def environment():
    if (ROOT / '.env').exists():
        raise SystemExit('Unexpected .env in isolated checkout')
    return {
        'HOME': str(Path.home()), 'TMPDIR': '/private/tmp',
        'PATH': f'{RUNTIME}/venv313/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
        'LANG': 'en_US.UTF-8', 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
        'CI': 'true',
        'PYTHONDONTWRITEBYTECODE': '1', 'DJANGO_SETTINGS_MODULE': 'config.settings_test_pg',
        'MAIL_ENABLED': '0',
        'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
        'TELEGRAM_BOT_TOKEN': '', 'TELEGRAM_WEBHOOK_SECRET': '',
        # Тесты сами включают fake. Общая подмена поставщика чата
        # искажала бы проверки интерфейса без ключа поставщика.
        'AI_PROVIDER': 'fake',
        'OLYMPIAD_AI_CHECK': '0', 'SMART_SEARCH_WARMUP': '0', 'YANDEX_METRIKA_ID': '',
        'DATABASE_URL': 'postgres://calc2_synthetic@127.0.0.1:61383/calc2_synthetic',
        'TEST_DATABASE_NAME': 'test_calc2_astra', 'REDIS_URL': 'redis://127.0.0.1:61384',
        'SECRET_KEY': 'SyntheticOnly-7Kw2mZv9Lp4Rt6Wy8Bn3Cf5Hj1Dg0SaQwErTyUiOpAsDfGh',
        'ALLOWED_HOSTS': 'example.org,www.example.org',
        'CALC2_BASE_URL': 'http://127.0.0.1:8113',
    }


def main():
    groups = {
        'lint': [[PYTHON, '-m', 'ruff', 'check', '.']],
        'security': [
            [PYTHON, '-m', 'bandit', '-r', 'problems', 'catalog', 'teacher', 'student', 'game', 'calc2', 'config', 'olympiads', 'vp', '-ll'],
            [PYTHON, '-m', 'pip_audit', '-r', 'requirements/base.txt'],
        ],
        'migrations': [[PYTHON, 'manage.py', 'migrate', '--noinput', '--settings=config.settings_test_pg'],
                       [PYTHON, 'manage.py', 'makemigrations', '--check', '--dry-run', '--settings=config.settings_test_pg']],
        'tests': [[PYTHON, 'scripts/run_tests.py', 'problems', 'catalog', 'teacher', 'student', 'calc2', 'game', 'calendar_stub', 'config', 'olympiads', 'vp', '--settings=config.settings_test_pg', '--verbosity', '2', '--parallel', '2', '--noinput']],
        'cache': [[PYTHON, 'manage.py', 'test', 'config.tests.test_cache_and_sessions',
                   '--settings=config.settings_test_pg', '--verbosity', '2', '--noinput']],
        'calc2': [[PYTHON, 'manage.py', 'test', 'calc2', '--settings=config.settings_test_pg',
                   '--verbosity', '2', '--noinput']],
        'deploy': [[PYTHON, 'manage.py', 'check', '--deploy', '--fail-level', 'WARNING', '--settings=config.settings_production']],
    }
    group = sys.argv[1]
    if group not in groups:
        raise SystemExit('Choose lint/security/migrations/tests/deploy/cache/calc2')
    LOGS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    results = []
    for i, command in enumerate(groups[group]):
        log = LOGS / f'{group}-{stamp}-{i}.log'
        start = time.monotonic()
        with log.open('w') as output:
            code = subprocess.call(command, cwd=ROOT, env=environment(), stdout=output, stderr=subprocess.STDOUT)
        result = {'command': command[1:], 'code': code, 'seconds': round(time.monotonic() - start, 1), 'log': str(log)}
        results.append(result)
        print(json.dumps(result), flush=True)
    (LOGS / f'{group}-{stamp}.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(r['code'] for r in results))


if __name__ == '__main__':
    sys.exit(main())
