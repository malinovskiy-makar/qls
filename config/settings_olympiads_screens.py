"""Настройки ночи 30→31.10.2026: экраны раздела «Олимпиады» на копии базы.

Наследует основные и подменяет только базу и два флага раздела. База —
`db_screens.sqlite3`, копия, которую владелец сделал перед запуском ночи;
основную `db.sqlite3` и копию сессии импорта `db_import.sqlite3` эти
настройки не открывают вовсе. Файл копии в git не попадает (`*.sqlite3`).

    ./venv313/bin/python manage.py runserver 8097 \
        --settings=config.settings_olympiads_screens --noreload
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_screens.sqlite3',  # noqa: F405
        'OPTIONS': {'timeout': 20},
    }
}

# Раздел открыт публике — на площадке ночи смотрим его глазами гостя.
OLYMPIADS_PUBLIC = True

# ИИ-проверка решения тура по критериям жюри (Э7). На бою выключена до
# правовой части; здесь включена, чтобы увидеть экраны целиком.
OLYMPIAD_AI_CHECK = True
