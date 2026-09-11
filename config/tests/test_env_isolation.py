# -*- coding: utf-8 -*-
"""Прогон тестов не зависит от `.env` разработчика.

⚠️ ЗАВЕДЕНО ПО НАСТОЯЩЕЙ ПОЛОМКЕ. На машине владельца в `.env` лежат ключ
модели и `SMART_SEARCH_RERANK=1`; `config/settings.py` читает этот файл
(`_load_dotenv_if_present`) — и пять модулей тестов `catalog` краснели
только у него. В CI переменных нет, там зелено, и это ПРЯЧЕТ настоящие
поломки: «у меня красное, а в CI зелёное» перестаёт быть сигналом.

Лечится в тестовой инфраструктуре, а не в настройках: бегун
`config.test_runner.EnvIsolatedRunner` затирает ключи поставщиков и гасит
флаг сортировщика на время прогона. Продакшен-код при этом не тронут —
вне прогона тестов бегун не участвует вовсе.

Тестам, которым ключ или флаг НУЖЕН, ничего не сломано: `override_settings`
и `mock.patch.dict(os.environ, ...)` ложатся поверх чистого состояния.
"""
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner

from config.test_runner import EnvIsolatedRunner, provider_key_env_names, scrub_environment


class RunnerWiredInTests(SimpleTestCase):
    """Бегун именно подключён. Без этого три проверки ниже ничего не значат."""

    def test_test_runner_setting_points_at_isolated_runner(self):
        self.assertEqual(settings.TEST_RUNNER,
                         'config.test_runner.EnvIsolatedRunner')


class LiveRunStateTests(SimpleTestCase):
    """Состояние ПРЯМО СЕЙЧАС, внутри идущего прогона."""

    def test_rerank_flag_is_off(self):
        self.assertFalse(
            settings.SMART_SEARCH_RERANK,
            'SMART_SEARCH_RERANK протёк в прогон из .env разработчика',
        )

    def test_provider_keys_are_empty(self):
        грязные = [имя for имя in provider_key_env_names()
                   if os.environ.get(имя, '').strip()]
        self.assertEqual(грязные, [],
                         'ключи поставщиков протекли в прогон из .env')


class ScrubMechanismTests(SimpleTestCase):
    """Сам механизм: подкладываем «грязное» окружение и проверяем зачистку.

    Проверки выше пройдут и на машине, где `.env` вовсе нет. Эта — нет:
    она сама создаёт ту грязь, от которой защищаемся.
    """

    def test_scrub_clears_keys_and_flag(self):
        имена = provider_key_env_names()
        self.assertIn('GLM_API_KEY', имена)

        подмена = {имя: 'секрет-из-env' for имя in имена}
        подмена['SMART_SEARCH_RERANK'] = '1'
        прежние = {имя: os.environ.get(имя) for имя in подмена}
        os.environ.update(подмена)
        try:
            with self.settings(SMART_SEARCH_RERANK=True):
                scrub_environment()
                for имя in имена:
                    self.assertEqual(os.environ.get(имя, ''), '',
                                     'ключ %s не зачищен' % имя)
                self.assertFalse(settings.SMART_SEARCH_RERANK)
        finally:
            for имя, значение in прежние.items():
                if значение is None:
                    os.environ.pop(имя, None)
                else:
                    os.environ[имя] = значение

    def test_scrub_runs_inside_setup_test_environment(self):
        """Зачистка висит на штатном шаге бегуна, а не на ручном вызове.

        Родительский `setup_test_environment` подменён: настоящий нельзя
        вызвать второй раз внутри уже идущего прогона. Подменено ровно
        то, что мешает, — проверяется наш собственный шаг.
        """
        бегун = EnvIsolatedRunner(interactive=False, verbosity=0)
        os.environ['GLM_API_KEY'] = 'секрет-из-env'
        try:
            with mock.patch.object(DiscoverRunner, 'setup_test_environment'):
                бегун.setup_test_environment()
            self.assertEqual(os.environ.get('GLM_API_KEY', ''), '')
        finally:
            os.environ.pop('GLM_API_KEY', None)


class SurvivesDotenvReloadTests(SimpleTestCase):
    """Зачистка переживает повторное чтение `.env`.

    ⚠️ ЭТО НЕ ТЕОРИЯ. На `--parallel` Windows поднимает воркеры через
    spawn: каждый заново импортирует `config/settings.py`, а тот заново
    читает `.env`. Зачистка, сделанная только в родителе, в воркерах
    отменялась — и пять модулей `catalog` продолжали краснеть, хотя
    одиночный прогон был зелёным.

    Держится это на `os.environ.setdefault` в `_load_dotenv_if_present`:
    уже заданная переменная сильнее файла. Поэтому зачистка выставляет
    ПУСТОЕ ЗНАЧЕНИЕ, а не удаляет ключ.
    """

    def test_dotenv_does_not_refill_scrubbed_keys(self):
        from config.settings import _load_dotenv_if_present

        подложный = Path(self.enterContext(tempfile.TemporaryDirectory()))
        файл = подложный / '.env'
        файл.write_text('GLM_API_KEY=секрет-из-файла\n'
                        'SMART_SEARCH_RERANK=1\n', encoding='utf-8')

        прежние = {имя: os.environ.get(имя)
                   for имя in ('GLM_API_KEY', 'SMART_SEARCH_RERANK')}
        try:
            scrub_environment()
            _load_dotenv_if_present(файл)
            self.assertEqual(os.environ.get('GLM_API_KEY', ''), '')
            self.assertEqual(os.environ.get('SMART_SEARCH_RERANK', ''), '')
        finally:
            for имя, значение in прежние.items():
                if значение is None:
                    os.environ.pop(имя, None)
                else:
                    os.environ[имя] = значение
