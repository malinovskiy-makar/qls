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
        # ⚠️ IMMEDIATE: автосохранение (по уходу фокуса) и «Сдать задание»
        # пишут одновременно; отложенная транзакция SQLite не может поднять
        # блокировку и сразу падает «database is locked» (Э9, телефон). На бою
        # PostgreSQL — это настройка только площадки ночи.
        'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'},
    }
}

# Раздел открыт публике — на площадке ночи смотрим его глазами гостя.
OLYMPIADS_PUBLIC = True

# ИИ-проверка решения тура по критериям жюри (Э7). На бою выключена до
# правовой части; здесь включена, чтобы увидеть экраны целиком.
OLYMPIAD_AI_CHECK = True

# Поставщик модели на площадке ночи. Ключей в окружении ночи нет, поэтому для
# снимков и сквозного прохода (Э9) сервер можно поднять с подставным:
#   NIGHT_AI_PROVIDER=fake QLS_FAKE_REPLY="$(cat …)" ./venv313/bin/python manage.py runserver …
# По умолчанию — как у сайта (без ключа проверка честно «недоступна»).
import os  # noqa: E402

if os.environ.get('NIGHT_AI_PROVIDER'):
    AI_PROVIDER = os.environ['NIGHT_AI_PROVIDER']
    # Чат «Оспорить оценку» ходит через поставщика чата «Стола» (GLM на бою).
    CATALOG_CHAT_PROVIDER = os.environ['NIGHT_AI_PROVIDER']
    CATALOG_CHAT_VISION_MODEL = ''
