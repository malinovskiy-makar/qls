"""Запуск собственной проверки с чистым окружением; реальные .env запрещены.

python3 claude/calc2_astra_20261102/run_local.py manage migrate --noinput
python3 claude/calc2_astra_20261102/run_local.py manage runserver 127.0.0.1:8113 --noreload
python3 claude/calc2_astra_20261102/run_local.py node calc2/tests/control_numbers.mjs
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path('/private/tmp/calc2-astra-runtime-20261102')
SETTINGS = 'claude.calc2_astra_20261102.settings_local'


def main():
    if (ROOT / '.env').exists():
        raise SystemExit('Останов: в изолированной копии найден .env.')
    (ROOT / '.calc2-astra-local').mkdir(exist_ok=True)
    env = {
        'HOME': str(Path.home()),
        'TMPDIR': '/private/tmp',
        'PATH': f'{RUNTIME}/venv313/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
        'LANG': 'en_US.UTF-8',
        'PYTHONUTF8': '1',
        'PYTHONDONTWRITEBYTECODE': '1',
        'DJANGO_SETTINGS_MODULE': SETTINGS,
        'SITE_ENV': 'dev',
        'MAIL_ENABLED': '0',
        'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
        'TELEGRAM_BOT_TOKEN': '',
        'TELEGRAM_WEBHOOK_SECRET': '',
        'AI_PROVIDER': 'fake',
        'CATALOG_CHAT_PROVIDER': 'fake',
        'OLYMPIAD_AI_CHECK': '0',
        'SMART_SEARCH_WARMUP': '0',
        'REDIS_URL': '',
        'YANDEX_METRIKA_ID': '',
        'QLS_TEST_LOCAL_CACHE': '1',
        'CALC2_BASE_URL': 'http://127.0.0.1:8113',
    }
    # Только несекретные параметры приборов, а не окружение оболочки.
    for key in ('ENGINES', 'WIDTHS', 'SHOTS', 'CHECK'):
        if key in os.environ:
            env[key] = os.environ[key]
    kind, *args = sys.argv[1:]
    if kind == 'manage':
        cmd = [str(RUNTIME / 'venv313/bin/python'), 'manage.py', *args]
    elif kind == 'node':
        cmd = [shutil.which('node', path=env['PATH']), *args]
    elif kind == 'python':
        cmd = [str(RUNTIME / 'venv313/bin/python'), *args]
    else:
        raise SystemExit('Первый аргумент: manage, node или python.')
    return subprocess.call(cmd, cwd=ROOT, env=env)


if __name__ == '__main__':
    sys.exit(main())
