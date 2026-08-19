# -*- coding: utf-8 -*-
"""Настройки ТОЛЬКО для осмотра страниц ошибок глазами.

⚠️ В бою не используются и на прод не едут. Нужны для одного: при
`DEBUG=True` Django рисует свою жёлтую отладочную страницу и до наших
шаблонов 400/403/404/500 не доходит вовсе. Чтобы владелец увидел то же,
что увидит человек на сервере, нужен `DEBUG=False` — а с ним локальный
сервер перестаёт отдавать статику, поэтому запускать с `--insecure`.

```bash
venv313/Scripts/python.exe manage.py runserver 8123 --insecure \\
    --settings=config.settings_errorcheck
```

Открыть: `/такой-страницы-нет/` (404) и `/oshibka-500/` (500).
"""
from config.settings import *  # noqa: F401,F403
from config.settings import BASE_DIR, TEMPLATES  # noqa: F401

DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']

# Отдельная база, чтобы осмотр не трогал витрину владельца.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

ROOT_URLCONF = 'config.urls_errorcheck'
