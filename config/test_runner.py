# -*- coding: utf-8 -*-
"""Бегун тестов, отвязывающий прогон от `.env` разработчика.

Зачем. `config/settings.py` читает `.env` из корня репозитория. У владельца
там лежат настоящий ключ модели и `SMART_SEARCH_RERANK=1` — и пять модулей
тестов `catalog` краснели только на его машине. В CI этих переменных нет,
джоб зелёный, и расхождение «у меня красное, в CI зелёное» перестаёт быть
сигналом настоящей поломки.

⚠️ ПОЧЕМУ БЕГУН, А НЕ ПРАВКА НАСТРОЕК. `config/settings.py` — боевой файл:
его читает и прод. Зачистка в нём означала бы ветку «а мы сейчас в тестах?»
внутри продакшен-кода. Бегун же участвует ТОЛЬКО в `manage.py test`: вне
прогона этот модуль не импортируется вовсе.

⚠️ ЗАЧИЩАЕМ И ОКРУЖЕНИЕ, И НАСТРОЙКУ. Поставщики читают ключ из
`os.environ` в момент вызова, а `settings.SMART_SEARCH_RERANK` посчитан
один раз при загрузке настроек — поэтому одного места мало.

Тестам, которым ключ или флаг НУЖЕН, ничего не сломано: `override_settings`
и `mock.patch.dict(os.environ, ...)` ложатся поверх чистого состояния.
Сторож самой зачистки — `config/tests/test_env_isolation.py`.
"""
import os

from django.test.runner import DiscoverRunner

# Флаги, которые обязаны быть в умолчательном состоянии, чем бы ни был
# заполнен `.env`. Значение — то, которое даёт код БЕЗ переменной окружения.
FLAG_DEFAULTS = {
    'SMART_SEARCH_RERANK': False,
}


def provider_key_env_names():
    """Имена переменных с ключами всех поставщиков — из самого реестра.

    Списком в этом файле не держим: добавят шестого поставщика — список
    молча устареет, а сторож останется зелёным.
    """
    from problems.ai.providers import PROVIDERS

    имена = {getattr(класс, 'key_env', '') for класс in PROVIDERS.values()}
    return sorted(имя for имя in имена if имя)


def scrub_environment():
    """Погасить в процессе ключи поставщиков и вернуть флаги к умолчанию.

    ⚠️ ПУСТОЕ ЗНАЧЕНИЕ, А НЕ `del`. `_load_dotenv_if_present` в настройках
    кладёт значения через `os.environ.setdefault`: уже заданная переменная
    сильнее файла. Удалённый ключ `.env` вернул бы обратно — и именно это
    происходило на `--parallel`, где Windows поднимает воркеры через spawn
    и каждый заново импортирует `config/settings.py` вместе с чтением
    `.env`. Пустая строка переживает такое перечитывание.
    """
    from django.conf import settings

    for имя in provider_key_env_names():
        os.environ[имя] = ''

    for имя, умолчание in FLAG_DEFAULTS.items():
        os.environ[имя] = ''
        setattr(settings, имя, умолчание)


class EnvIsolatedRunner(DiscoverRunner):
    """`DiscoverRunner` + зачистка окружения перед сбором тестов."""

    def setup_test_environment(self, **kwargs):
        scrub_environment()
        super().setup_test_environment(**kwargs)
