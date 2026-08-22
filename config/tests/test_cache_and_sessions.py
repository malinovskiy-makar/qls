# -*- coding: utf-8 -*-
"""Кэш и сессии: проверки, которые краснеют при возвращении мин №2 и №3.

Мина №2 — кэш не общий между воркерами. При `LocMemCache` девять воркеров
держат девять независимых кэшей: попадание примерно один раз из девяти,
а сброс индекса поиска доходит до одного воркера из девяти.

Мина №3 — сессии в базе. Каждое чтение сессии — запрос в PostgreSQL.

⚠️ ЭТИ ТЕСТЫ ЛЕЖАТ В `config/`, А НЕ В `problems/`, НАМЕРЕННО: они проверяют
настройки проекта, а не поведение приложения. Из-за этого приложение `config`
ПРИШЛОСЬ ДОПИСАТЬ В СПИСОК ДЖОБА `tests` в .github/workflows/ci.yml —
там приложения перечислены поимённо, и без правки эти тесты в CI просто
не запускались бы. Локальный `manage.py test` без аргументов находит их сам.
"""
import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from django.conf import settings
from django.core.cache import caches
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, tag

from catalog import semantic

# Живой Redis есть ровно тогда, когда задан REDIS_URL. Значение не печатаем
# нигде: в нём может быть пароль.
REDIS_URL = os.environ.get('REDIS_URL', '').strip()

# GitHub Actions выставляет CI=true всегда. По этому признаку отличаем
# «Redis честно недоступен» от «Redis забыли подключить в CI».
IN_CI = bool(os.environ.get('CI'))


def _session_store():
    """Класс хранилища сессий — тот, который РЕАЛЬНО выбран настройками.

    Берём по `settings.SESSION_ENGINE`, а не жёстким импортом: иначе тест
    проверял бы cached_db даже после того, как кто-то сменил движок.
    """
    return importlib.import_module(settings.SESSION_ENGINE).SessionStore


# ─────────────────────────────────────────────────────────────────────────
# Тест 1. Два алиаса, и это РАЗНЫЕ хранилища.
# ─────────────────────────────────────────────────────────────────────────
class CachesLayoutTests(SimpleTestCase):

    # ⚠️ СМЫСЛ ЭТИХ ПРОВЕРОК — «АЛИАСЫ НЕ СХЛОПНУЛИСЬ», А НЕ ИХ ЧИСЛО.
    # Раньше тут стояло `== {'default', 'sessions'}`, и 22.08 он честно
    # покраснел на добавлении третьего алиаса `search` (векторы поисковых
    # запросов, С4). Красным он был по форме, а не по существу: беда,
    # которую он сторожит, — это когда двум РАЗНЫМ вещам достаётся ОДНО
    # хранилище, потому что `cache.clear()` у Redis это FLUSHDB. Появление
    # нового отдельного хранилища такой бедой не является.
    ОБЯЗАТЕЛЬНЫЕ_АЛИАСЫ = {'default', 'sessions', 'search'}

    def test_обязательные_алиасы_на_месте(self):
        self.assertLessEqual(
            self.ОБЯЗАТЕЛЬНЫЕ_АЛИАСЫ, set(settings.CACHES),
            'Пропал алиас кэша. default — кэш приложения, sessions — сессии, '
            'search — векторы поисковых запросов (С4). Схлопывание любых двух '
            'в один означает общее хранилище, а cache.clear() у Redis — это '
            'FLUSHDB на всю базу.',
        )

    def test_все_алиасы_указывают_на_разные_хранилища(self):
        места = {}
        for алиас in sorted(settings.CACHES):
            место = settings.CACHES[алиас].get('LOCATION')
            self.assertTrue(место, 'у %s не задан LOCATION' % алиас)
            self.assertNotIn(
                место, места,
                'Алиасы %s и %s указывают на одно хранилище (%s). Для Redis '
                'это одна база, и FLUSHDB при cache.clear() унесёт чужое: '
                'сессии — разлогинит людей, векторы запросов — заставит '
                'заново будить модель. Для LocMemCache одинаковый LOCATION — '
                'один склад под двумя вывесками, та же беда в разработке.'
                % (места.get(место), алиас, место),
            )
            места[место] = алиас

    def test_экземпляры_кэша_не_видят_ключей_друг_друга(self):
        """Проверка не по настройкам, а по поведению: положили в один —
        в остальных пусто. Настройки можно написать правильно и всё равно
        получить один объект (так было бы у LocMemCache без LOCATION)."""
        caches['default'].set('проба-разделения', 'из-кэша', 60)
        self.addCleanup(caches['default'].delete, 'проба-разделения')
        for алиас in settings.CACHES:
            if алиас == 'default':
                continue
            self.assertIsNone(
                caches[алиас].get('проба-разделения'),
                'Алиас %s видит ключ, положенный в default' % алиас)


# ─────────────────────────────────────────────────────────────────────────
# Тест 2. Движок сессий.
# ─────────────────────────────────────────────────────────────────────────
class SessionEngineTests(SimpleTestCase):

    def test_движок_сессий_cached_db(self):
        self.assertEqual(
            settings.SESSION_ENGINE,
            'django.contrib.sessions.backends.cached_db',
            'Движок сессий обязан быть cached_db. Чистый "cache" на сервере '
            'с политикой вытеснения allkeys-lru означает, что под нагрузкой '
            'Redis выбросит сессии и люди разлогинятся посреди работы. '
            'Обоснование — docs/adr/0011-redis-cache-and-sessions.md.',
        )

    def test_сессии_берут_свой_алиас(self):
        self.assertEqual(getattr(settings, 'SESSION_CACHE_ALIAS', None),
                         'sessions')

    def test_сессия_не_переписывается_на_каждый_запрос(self):
        """SESSION_SAVE_EVERY_REQUEST=True означает запись сессии в базу на
        КАЖДЫЙ запрос, включая те, что сессию не трогали. При cached_db это
        сводит на нет половину выигрыша."""
        self.assertFalse(getattr(settings, 'SESSION_SAVE_EVERY_REQUEST', False))


# ─────────────────────────────────────────────────────────────────────────
# Тест 3. Боевые настройки без REDIS_URL обязаны падать при старте.
# ─────────────────────────────────────────────────────────────────────────
class ProductionRequiresRedisTests(SimpleTestCase):
    """Модуль боевых настроек загружается ОТДЕЛЬНОЙ копией под другим именем.

    `importlib.reload` здесь не годится: он подменил бы настоящий
    `config.settings_production` в sys.modules половиной выполненного модуля,
    и следующий тест получил бы мусор.
    """

    PROD_PATH = Path(settings.BASE_DIR) / 'config' / 'settings_production.py'

    # Правдоподобное окружение без REDIS_URL. Ключ длинный и разнобуквенный
    # намеренно — на коротком поднялась бы посторонняя проверка security.W009.
    BASE_ENV = {
        'SECRET_KEY': 'x7Kq2mZv9Lp4Rt6Wy8Bn3Cf5Hj1Dg0Sa-QwErTyUiOpAsDfGhJkLzXcVbNm',
        'ALLOWED_HOSTS': 'example.org',
        'DATABASE_URL': 'postgres://u:p@127.0.0.1:5432/db',
        'PATH': os.environ.get('PATH', ''),
    }

    def _load_production(self, env):
        spec = importlib.util.spec_from_file_location(
            'config._settings_production_probe', self.PROD_PATH)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, env, clear=True):
            spec.loader.exec_module(module)
        return module

    def test_без_redis_url_боевые_настройки_падают(self):
        with self.assertRaises(ImproperlyConfigured) as поймано:
            self._load_production(dict(self.BASE_ENV))
        self.assertIn('REDIS_URL', str(поймано.exception))

    def test_с_redis_url_боевые_настройки_поднимаются(self):
        """Обратная сторона: предохранитель не должен срабатывать зря."""
        env = dict(self.BASE_ENV, REDIS_URL='redis://127.0.0.1:6379')
        module = self._load_production(env)
        # Подмножеством, а не равенством: смысл проверки — что боевые
        # настройки поднялись и алиасы на месте, а не что их ровно столько.
        # См. комментарий у ОБЯЗАТЕЛЬНЫЕ_АЛИАСЫ выше.
        self.assertLessEqual({'default', 'sessions', 'search'},
                             set(module.CACHES))
        self.assertEqual(module.SESSION_ENGINE,
                         'django.contrib.sessions.backends.cached_db')


# ─────────────────────────────────────────────────────────────────────────
# Тест 1-бис. Сам выбор бэкенда — на настоящем `config/settings.py`.
# ─────────────────────────────────────────────────────────────────────────
class SettingsBackendChoiceTests(SimpleTestCase):
    """`config/settings.py` загружается ОТДЕЛЬНОЙ копией с подставленным
    окружением.

    ⚠️ ПОЧЕМУ НЕ ЧЕРЕЗ `settings_production`. Там стоит `from .settings
    import *`, а `config.settings` к моменту прогона уже лежит в
    `sys.modules` — значит файл НЕ выполняется заново, и подставленное
    окружение до него не доходит. Первая версия этого теста именно на этом
    и попалась: она думала, что проверяет разбор адреса, а не проверяла
    ничего. Поэтому файл читается напрямую.
    """

    SETTINGS_PATH = Path(settings.BASE_DIR) / 'config' / 'settings.py'

    def _load_settings(self, env):
        spec = importlib.util.spec_from_file_location(
            'config._settings_probe', self.SETTINGS_PATH)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, env, clear=True):
            spec.loader.exec_module(module)
        return module

    def test_с_redis_url_оба_алиаса_на_redis_и_в_разных_базах(self):
        module = self._load_settings({'REDIS_URL': 'redis://127.0.0.1:6379'})
        for алиас in ('default', 'sessions'):
            self.assertEqual(module.CACHES[алиас]['BACKEND'],
                             'django.core.cache.backends.redis.RedisCache')
        self.assertNotEqual(module.CACHES['default']['LOCATION'],
                            module.CACHES['sessions']['LOCATION'])

    def test_прогон_тестов_уводится_на_базы_15_и_14(self):
        """⚠️ САМАЯ ВАЖНАЯ ЗАЩИТА ЭТОГО ФАЙЛА. Тесты зовут cache.clear(), а
        у Redis это FLUSHDB. Шёл бы прогон по базам 0 и 1 — он вычистил бы
        рабочий кэш и рабочие сессии того, кто его запустил.

        Признак «идёт прогон» берётся из sys.argv, а этот тест сам выполняется
        внутри прогона, поэтому проверка честная: подставлять ничего не надо.
        """
        self.assertIn('test', __import__('sys').argv,
                      'признак прогона тестов сломан — проверка ниже потеряла смысл')
        module = self._load_settings({'REDIS_URL': 'redis://127.0.0.1:6379'})
        self.assertTrue(module.CACHES['default']['LOCATION'].endswith('/15'),
                        'кэш прогона тестов обязан жить в базе Redis 15')
        self.assertTrue(module.CACHES['sessions']['LOCATION'].endswith('/14'),
                        'сессии прогона тестов обязаны жить в базе Redis 14')

    def test_без_redis_url_два_разных_locmem(self):
        module = self._load_settings({})
        for алиас in ('default', 'sessions'):
            self.assertEqual(module.CACHES[алиас]['BACKEND'],
                             'django.core.cache.backends.locmem.LocMemCache')
        self.assertNotEqual(
            module.CACHES['default']['LOCATION'],
            module.CACHES['sessions']['LOCATION'],
            'Одинаковый LOCATION у двух LocMemCache — это один и тот же склад '
            'под двумя вывесками.')

    def test_сломанный_redis_url_падает_при_старте(self):
        """Пароль с непроцентно-закодированным символом ломает разбор адреса.
        Это должно быть видно при старте, а не пятисоткой у посетителя."""
        for плохой in ('это вообще не адрес', 'redis://', 'http://127.0.0.1'):
            with self.subTest(адрес=плохой):
                with self.assertRaises(ValueError):
                    self._load_settings({'REDIS_URL': плохой})


# ─────────────────────────────────────────────────────────────────────────
# Тест 4. ГЛАВНЫЙ ТЕСТ МИНЫ №3: сброс кэша не разлогинивает.
# ─────────────────────────────────────────────────────────────────────────
class CacheClearKeepsSessionsTests(TestCase):

    def test_сброс_кэша_не_уносит_сессию(self):
        store_cls = _session_store()

        # 1. Кладём что-нибудь в кэш приложения.
        caches['default'].set('маркер-кэша', 'значение-в-кэше', 300)

        # 2. Заводим сессию с данными и запоминаем её ключ.
        сессия = store_cls()
        сессия['роль'] = 'ученик'
        сессия['счёт'] = 42
        сессия.create()
        ключ = сессия.session_key
        self.assertTrue(ключ)

        # 3. Сбрасываем кэш приложения. У Redis это FLUSHDB — вычищается
        #    ВСЯ база Redis, а не только ключи алиаса default.
        caches['default'].clear()

        # 4. Кэш действительно пуст...
        self.assertIsNone(caches['default'].get('маркер-кэша'),
                          'cache.clear() не сработал — тест бессмысленен')

        # 5. ...А СЕССИЯ ЖИВА, и её данные читаются.
        заново = store_cls(session_key=ключ)
        self.assertEqual(заново.get('роль'), 'ученик',
                         'Сессия не пережила сброс кэша. Значит сессии и кэш '
                         'делят хранилище, и любой cache.clear() разлогинивает '
                         'всех до одного.')
        self.assertEqual(заново.get('счёт'), 42)

    def test_вошедший_пользователь_переживает_сброс_кэша(self):
        """То же самое, но целиком через настоящий вход и клиент Django —
        так проверяется вся цепочка middleware, а не только хранилище."""
        from problems.models import User

        User.objects.create_user(username='кэш-тест', password='пароль-теста-123')
        self.assertTrue(self.client.login(username='кэш-тест',
                                          password='пароль-теста-123'))
        caches['default'].clear()
        self.assertIn('_auth_user_id', self.client.session,
                      'После сброса кэша пользователь оказался разлогинен.')


# ─────────────────────────────────────────────────────────────────────────
# Тест 5. МИНА №2 в части индекса поиска: инвалидация между процессами.
# ─────────────────────────────────────────────────────────────────────────
class IndexVersionTests(SimpleTestCase):
    """Два процесса имитируются одним модулем.

    `_index` и `_index_version` — переменные уровня модуля, то есть ровно
    то, что у каждого воркера своё. «Переключиться на второй процесс» =
    руками вернуть его слепок этих переменных.
    """

    ПУСТАЯ_МАТРИЦА = np.empty((0, 8), dtype=np.float32)

    def setUp(self):
        self.сборок = 0
        self._было = (semantic._index, semantic._index_version)
        self.addCleanup(self._вернуть_как_было)

        caches['default'].delete(semantic._VERSION_KEY)
        semantic._index = None
        semantic._index_version = None

        патч = mock.patch.object(semantic, '_build_index',
                                 side_effect=self._поддельная_сборка)
        патч.start()
        self.addCleanup(патч.stop)

    def _вернуть_как_было(self):
        semantic._index, semantic._index_version = self._было
        caches['default'].delete(semantic._VERSION_KEY)

    def _поддельная_сборка(self):
        self.сборок += 1
        return {'matrix': self.ПУСТАЯ_МАТРИЦА, 'ids': [],
                'is_test_flags': [], 'номер_сборки': self.сборок}

    def test_без_причины_индекс_не_пересобирается(self):
        """Страховка от «зелёного по неправильной причине»: реализация,
        которая пересобирает индекс на каждый вызов, прошла бы оба теста
        ниже, но убила бы поиск."""
        первый = semantic.get_index()
        второй = semantic.get_index()
        self.assertIs(первый, второй)
        self.assertEqual(self.сборок, 1)

    def test_сброс_доходит_до_второго_процесса(self):
        индекс_1 = semantic.get_index()          # «процесс 1» построил индекс
        версия_1 = semantic._index_version

        semantic.invalidate_index()              # сброс сделан в процессе 1

        # Переключаемся на «процесс 2»: он про сброс ничего не знает и
        # держит свой старый индекс со старой версией.
        semantic._index = индекс_1
        semantic._index_version = версия_1

        индекс_2 = semantic.get_index()
        self.assertIsNot(
            индекс_2, индекс_1,
            'Второй процесс остался со старым индексом: invalidate_index() '
            'не дошёл до него. На девяти воркерах это восемь воркеров, '
            'отвечающих по устаревшему индексу.')

    def test_после_сброса_всего_кэша_индекс_считается_устаревшим(self):
        """cache.clear() уносит и сам ключ версии. Отсутствие ключа обязано
        означать «перестроить», а не «версия 1»: иначе процесс, у которого
        локально уже лежала «версия 1», решит, что ничего не изменилось."""
        индекс_1 = semantic.get_index()
        версия_1 = semantic._index_version

        caches['default'].clear()                # FLUSHDB — ключа версии нет

        semantic._index = индекс_1               # «процесс 2» со старым индексом
        semantic._index_version = версия_1

        индекс_2 = semantic.get_index()
        self.assertIsNot(
            индекс_2, индекс_1,
            'После полного сброса кэша процесс остался со старым индексом.')

    def test_после_пересборки_процессы_сходятся_на_одной_версии(self):
        """Восстановленный ключ версии должен быть ОБЩИМ: иначе процессы
        пересобирали бы индекс бесконечно, на каждый поисковый запрос."""
        semantic.get_index()
        caches['default'].clear()
        semantic.get_index()                     # пересборка после сброса
        было = self.сборок
        semantic.get_index()
        semantic.get_index()
        self.assertEqual(self.сборок, было,
                         'Индекс пересобирается на каждый вызов.')


# ─────────────────────────────────────────────────────────────────────────
# Тест 6. Живой Redis. Пропускается без него — но не в CI.
# ─────────────────────────────────────────────────────────────────────────
# ⚠️ ПРИЧИНА МЕТКИ `serial` (без причины метку ставить запрещено, см.
# docs/TESTING.md): единственный класс, которому нужен НАСТОЯЩИЙ Redis.
# Параллельный шаг прогона намеренно уводит кэш в память процесса —
# иначе восемь воркеров писали бы в одну базу Redis и `cache.clear()`
# одного обнулял бы кэш остальным. Под LocMemCache эти проверки не
# пропустились бы, а УПАЛИ: `REDIS_URL` задан, значит `skipUnless` не
# срабатывает, а `settings.CACHES` при этом указывает на память.
# Поэтому класс идёт вторым шагом, где Redis снова настоящий.
@tag('serial')
@unittest.skipUnless(REDIS_URL, 'REDIS_URL не задан — живого Redis нет')
class RedisLiveTests(SimpleTestCase):

    def test_оба_алиаса_на_redis(self):
        for алиас in ('default', 'sessions'):
            self.assertEqual(
                settings.CACHES[алиас]['BACKEND'],
                'django.core.cache.backends.redis.RedisCache',
                f'алиас {алиас} не на Redis, хотя REDIS_URL задан')

    def test_прогон_тестов_уводится_на_базы_15_и_14(self):
        """⚠️ САМАЯ ВАЖНАЯ ЗАЩИТА ЭТОГО ФАЙЛА. Тесты зовут cache.clear(),
        а у Redis это FLUSHDB. Если бы прогон шёл по базам 0 и 1, он вычистил
        бы рабочий кэш и рабочие сессии того, кто его запустил."""
        self.assertTrue(settings.CACHES['default']['LOCATION'].endswith('/15'),
                        'кэш прогона тестов обязан жить в базе Redis 15')
        self.assertTrue(settings.CACHES['sessions']['LOCATION'].endswith('/14'),
                        'сессии прогона тестов обязаны жить в базе Redis 14')

    def test_flushdb_кэша_не_трогает_базу_сессий(self):
        """Поведенческая проверка того же самого, уже внутри Redis."""
        caches['sessions'].set('ключ-в-базе-сессий', 'цел', 300)
        self.addCleanup(caches['sessions'].delete, 'ключ-в-базе-сессий')
        caches['default'].set('ключ-в-базе-кэша', 'пропадёт', 300)

        caches['default'].clear()

        self.assertIsNone(caches['default'].get('ключ-в-базе-кэша'))
        self.assertEqual(caches['sessions'].get('ключ-в-базе-сессий'), 'цел',
                         'FLUSHDB кэша достал до базы сессий — значит база '
                         'одна и та же.')


class RedisMustRunInCiTests(SimpleTestCase):
    """Без этого теста джоб CI мог бы вечно ПРОПУСКАТЬ проверки Redis и
    оставаться зелёным — то есть быть зелёной галочкой напротив
    непроверенного пути."""

    @unittest.skipUnless(IN_CI, 'не CI — локально Redis не обязателен')
    def test_в_ci_redis_обязан_быть(self):
        self.assertTrue(
            REDIS_URL,
            'В CI не задан REDIS_URL, значит проверки Redis тихо пропущены. '
            'Служба redis и переменная REDIS_URL — в .github/workflows/ci.yml, '
            'джоб "tests".')
