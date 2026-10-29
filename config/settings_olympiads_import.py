"""Настройки прогона импорта пакета олимпиад на ИЗОЛИРОВАННОЙ копии базы.

Наследует основные и подменяет только `DATABASES`: база — снимок основной
`db.sqlite3` (штатный `sqlite3.Connection.backup()`, 30.10.2026), лежащий
рядом в `db_import.sqlite3`. Основную базу импорт не открывает вовсе: в её
папке параллельно идёт другая работа, и миграции под чужими ветками менять
нельзя. Файл копии в git не попадает (`*.sqlite3` в .gitignore).

    ./venv313/bin/python manage.py import_olympiads_kits <пакет> \
        --settings=config.settings_olympiads_import
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_import.sqlite3',  # noqa: F405
        'OPTIONS': {'timeout': 20},
    }
}
