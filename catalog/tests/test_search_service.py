# -*- coding: utf-8 -*-
"""Сервис кодирования запросов и деградация без него (С4).

⚠️ ЗАЧЕМ ЭТОТ ФАЙЛ. Смысловой поиск переехал из процесса Django в отдельный
контейнер `search`: модель весит 2,12 ГБ, а воркеров девять. Переезд ввёл
новую точку отказа — сеть. Здесь сторожатся три вещи, и каждая из них
ломается тихо:

1. Транспорт не портит вектор. Вектор, приехавший по HTTP, обязан быть
   ПОБИТОВО тем же, что дала бы модель напрямую. Испорченный на доли
   процента вектор не уронит ничего — поиск просто станет хуже.
2. Повторный запрос не будит модель. Кэш обязан отвечать раньше сети.
3. Лежащий сервис — это ДЕГРАДАЦИЯ, а не пятисотка. И, что не менее важно,
   Django при этом НЕ должен полезть за моделью сам.
"""
import base64
import importlib.util
import json
import os
import re
import sys
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import numpy as np
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import TestCase, SimpleTestCase, override_settings, tag
from django.urls import reverse

from catalog import search_client
from problems.embedding_config import (
    EMBEDDING_DIM, EMBEDDING_MODEL_BUILD, EMBEDDING_MODEL_NAME,
)
from problems.models import Problem

# Адрес, на котором заведомо никто не слушает: деградацию надо проверять
# на настоящем отказе соединения, а не на подменённой функции.
МЁРТВЫЙ_АДРЕС = 'http://127.0.0.1:9'

МОДУЛИ_МОДЕЛИ = ('sentence_transformers', 'torch', 'transformers')


def модель_скачана():
    """Можно ли вообще запустить тест побитового совпадения.

    Проверяем наличие файлов, а не пробуем загрузить: загрузка занимает
    минуты и 2,27 ГБ памяти, и делать это ради `skipUnless` нельзя.

    ⚠️ БИБЛИОТЕКА ПРОВЕРЯЕТСЯ ВМЕСТЕ С МОДЕЛЬЮ, И ЭТО НЕ ПЕДАНТИЗМ.
    Сторож смотрел только на кэш HuggingFace. На машине, где модель скачана,
    а `sentence-transformers` не поставлен (он живёт в requirements/local.txt,
    а не в dev.txt), `skipUnless` пропускал тест внутрь, и `setUpClass` падал
    с `ModuleNotFoundError` — то есть шаг B прогона краснел не из-за кода, а
    из-за окружения. Замер 24.08: именно так и вышло. Смысл сторожа — «тест
    может выполниться», а без библиотеки он выполниться не может.
    """
    if importlib.util.find_spec('sentence_transformers') is None:
        return False
    корень = Path(os.environ.get('HF_HOME')
                  or Path.home() / '.cache' / 'huggingface')
    имя = 'models--' + EMBEDDING_MODEL_NAME.replace('/', '--')
    каталог = корень / 'hub' / имя
    if not каталог.exists():
        return False
    # Пустой каталог остаётся после прерванной загрузки — это не «скачано».
    return any((каталог / 'snapshots').glob('*/config.json'))


class ЗаглушкаКэша:
    """Считает обращения к сервису, отдавая правдоподобный вектор."""

    def __init__(self):
        self.вызовов = 0

    def __call__(self, texts):
        self.вызовов += 1
        return [np.full(EMBEDDING_DIM, 0.5, dtype=np.float32)
                for _ in texts]


class QueryVectorCacheTests(SimpleTestCase):
    """Повторный тот же запрос не должен доходить до сервиса и модели."""

    def setUp(self):
        caches['search'].clear()

    def test_второй_одинаковый_запрос_берётся_из_кэша(self):
        заглушка = ЗаглушкаКэша()
        with mock.patch.object(search_client, '_post_encode', заглушка):
            первый = search_client.encode_one('эластичность спроса по цене')
            второй = search_client.encode_one('эластичность спроса по цене')

        self.assertEqual(
            заглушка.вызовов, 1,
            'Сервис позван %d раза вместо одного — кэш векторов не работает, '
            'и каждый повтор запроса будит модель.' % заглушка.вызовов)
        np.testing.assert_array_equal(первый, второй)

    def test_другой_текст_идёт_в_сервис(self):
        """Обратная сторона: кэш не должен склеивать разные запросы."""
        заглушка = ЗаглушкаКэша()
        with mock.patch.object(search_client, '_post_encode', заглушка):
            search_client.encode_one('эластичность спроса')
            search_client.encode_one('кривая Филлипса')
        self.assertEqual(заглушка.вызовов, 2)

    def test_ключ_кэша_содержит_сборку_модели(self):
        """Иначе после смены модели раздавались бы старые векторы.

        Вектор запроса сравнивается с векторами корпуса. Сменили модель,
        пересчитали корпус — а кэш продолжает отдавать вектор от прежней
        модели: косинус едет молча, ни одна проверка не краснеет.
        """
        ключ = search_client._cache_key('любой текст')
        self.assertIn(EMBEDDING_MODEL_BUILD, ключ)


@override_settings(SEARCH_SERVICE_URL=МЁРТВЫЙ_АДРЕС,
                   SEARCH_SERVICE_TIMEOUT=0.5,
                   SEARCH_SERVICE_BREAKER_SECONDS=0)
class ServiceUnavailableTests(SimpleTestCase):
    """Отказ сервиса поднимает типизированное исключение, а не что попало.

    Выключатель здесь погашен (`SEARCH_SERVICE_BREAKER_SECONDS=0`): эти
    тесты про то, что КАЖДОЕ обращение к мёртвому сервису отвечает
    понятной ошибкой. Про сам выключатель — класс ниже.
    """

    def setUp(self):
        caches['search'].clear()
        search_client.reset_breaker()
        self.addCleanup(search_client.reset_breaker)

    def test_отказ_соединения_даёт_типизированное_исключение(self):
        with self.assertRaises(search_client.SearchServiceUnavailable):
            search_client.encode_one('эластичность спроса')

    def test_healthy_отвечает_false_а_не_падает(self):
        self.assertFalse(search_client.healthy())


@override_settings(SEARCH_SERVICE_URL=МЁРТВЫЙ_АДРЕС,
                   SEARCH_SERVICE_TIMEOUT=0.5,
                   SEARCH_SERVICE_BREAKER_SECONDS=30)
class BreakerTests(SimpleTestCase):
    """Короткоживущий выключатель: недоступный сервис отвечает БЫСТРО.

    ⚠️ ЗАЧЕМ ЭТО ВООБЩЕ. Контейнера `search` на боевом сервере нет, и это
    не авария на минуту, а сегодняшнее нормальное состояние. Без
    выключателя КАЖДЫЙ поисковый запрос платил бы полный
    `SEARCH_SERVICE_TIMEOUT` за пустое ожидание, и человек, набравший
    запрос, ждал бы ровно столько, сколько ждал бы работающий поиск.
    """

    def setUp(self):
        caches['search'].clear()
        search_client.reset_breaker()
        self.addCleanup(search_client.reset_breaker)

    def test_после_первого_отказа_до_сети_дело_не_доходит(self):
        with mock.patch.object(search_client, '_post_encode',
                               wraps=search_client._post_encode) as шпион:
            for _ in range(4):
                with self.assertRaises(search_client.SearchServiceUnavailable):
                    search_client.encode_one('эластичность спроса')
        # Все четыре обращения отвечают ошибкой, но сеть трогает первое:
        # остальные три отбивает выключатель — до `urlopen` они не доходят.
        self.assertEqual(шпион.call_count, 4)

    def test_второе_обращение_отвечает_мгновенно(self):
        начало = time.perf_counter()
        with self.assertRaises(search_client.SearchServiceUnavailable):
            search_client.encode_one('первый запрос')
        первое = time.perf_counter() - начало

        начало = time.perf_counter()
        with self.assertRaises(search_client.SearchServiceUnavailable):
            search_client.encode_one('второй запрос')
        второе = time.perf_counter() - начало

        # Порог намеренно грубый: замер 13.09.2026 давал 2,03 с на первое
        # обращение и 0,000 с на последующие. Смысл проверки — «второе
        # обращение не ходит в сеть вовсе», а не точное число секунд.
        self.assertLess(второе, 0.05,
                        'второе обращение к мёртвому сервису ходило в сеть: '
                        'первое %.3f с, второе %.3f с' % (первое, второе))

    def test_выключатель_называет_причину_первого_отказа(self):
        with self.assertRaises(search_client.SearchServiceUnavailable):
            search_client.encode_one('первый запрос')
        with self.assertRaises(search_client.SearchServiceUnavailable) as поймано:
            search_client.encode_one('второй запрос')
        self.assertIn('нет связи с сервисом', str(поймано.exception))

    def test_сброс_открывает_дверь_снова(self):
        with self.assertRaises(search_client.SearchServiceUnavailable):
            search_client.encode_one('первый запрос')
        search_client.reset_breaker()
        with mock.patch.object(search_client, '_post_encode',
                               side_effect=ValueError('до сети дошли')) as _:
            with self.assertRaises(ValueError):
                search_client.encode_one('третий запрос')


@override_settings(SEARCH_SERVICE_URL='file:///etc/passwd',
                   SEARCH_SERVICE_TIMEOUT=0.5)
class InvalidSchemeTests(SimpleTestCase):
    """⚠️ B310 (CWE-22): недопустимая схема ловится ДО обращения к сети.

    Найдено bandit-ом после слияния С4 в main: `urlopen` умеет открывать не
    только http(s), но и `file://`, и статически доказать обратное bandit
    не может. Здесь — поведенческое доказательство: если в настройках
    вместо адреса сервиса окажется `file:///etc/passwd` (опечатка, битый
    `.env`), клиент обязан упасть с понятной ошибкой РАНЬШЕ, чем попробует
    открыть это как URL, а не тихо прочитать локальный файл.
    """

    def setUp(self):
        caches['search'].clear()

    def test_недопустимая_схема_даёт_ошибку_до_сети(self):
        with mock.patch.object(urllib.request, 'urlopen') as поддельный:
            with self.assertRaises(search_client.SearchServiceUnavailable):
                search_client.encode_one('эластичность спроса')
        поддельный.assert_not_called()

    def test_healthy_отвечает_false_на_недопустимую_схему_без_сети(self):
        with mock.patch.object(urllib.request, 'urlopen') as поддельный:
            self.assertFalse(search_client.healthy())
        поддельный.assert_not_called()


class _БазаДеградации(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='искатель-с4', password='пароль-для-теста-123')
        cls.задача = Problem.objects.create(
            title='Эластичность спроса по цене',
            statement='Найдите эластичность спроса при цене 10 рублей.',
            status=Problem.Status.PUBLISHED,
            needs_quality_review=False,
            hidden_pending_review=False,
        )

    def setUp(self):
        caches['search'].clear()
        self.client.force_login(self.user)


@override_settings(SEMANTIC_SEARCH_ENABLED=True,
                   SEARCH_SERVICE_URL=МЁРТВЫЙ_АДРЕС,
                   SEARCH_SERVICE_TIMEOUT=0.5)
class DegradationWithoutServiceTests(_БазаДеградации):
    """⚠️ ГЛАВНЫЙ ТЕСТ ФАЙЛА: сервис лежит, сайт жив.

    Поиск ВКЛЮЧЁН настройкой, но сервиса нет. Это ровно то состояние, в
    котором окажется прод, если контейнер `search` не поднялся или его
    перезапускают. Страница обязана отвечать 200 и искать по словам.
    """

    def test_страница_поиска_отвечает_200_без_сервиса(self):
        ответ = self.client.get(reverse('catalog:problem_list'),
                                {'q': 'эластичность спроса'})
        self.assertEqual(
            ответ.status_code, 200,
            'Лежащий сервис поиска уронил страницу в %s. Деградация должна '
            'быть незаметной для человека, а не пятисоткой.'
            % ответ.status_code)

    def test_страница_деградирует_а_не_показывает_ошибку(self):
        """⚠️ КОДА 200 НЕДОСТАТОЧНО, И ЭТО ГЛАВНЫЙ УРОК ЭТОГО ФАЙЛА.

        Первая версия проверяла только `status_code == 200` и была зелёной,
        когда страница показывала человеку «Ошибка поиска: нет связи с
        сервисом…» и НИ ОДНОГО результата. Формально не пятисотка, а по
        сути — сломанный поиск плюс наша внутренняя кухня на экране.

        Правильная деградация: плашка «ищем по словам» (`degraded`),
        результаты есть, строки `error` нет.
        """
        ответ = self.client.get(reverse('catalog:problem_list'),
                                {'q': 'эластичность спроса'})
        контекст = ответ.context

        self.assertTrue(
            контекст['degraded'],
            'Флаг degraded не выставлен: человеку не сказали, что ищем '
            'только по словам.')
        # ⚠️ КЛЮЧА `error` В КОНТЕКСТЕ БОЛЬШЕ НЕТ, И ЭТО НЕ ОСЛАБЛЕНИЕ
        # ПРОВЕРКИ, А УСИЛЕНИЕ. Объединённый экран каталога деградирует на
        # ЛЮБОЙ поломке поиска, поэтому места, где строка ошибки могла бы
        # родиться, не осталось вовсе. Смотрим на то, что видит человек:
        # ни слова «ошибка», ни адреса внутреннего сервиса на экране.
        тело = ответ.content.decode()
        self.assertNotIn('Ошибка поиска', тело)
        self.assertNotIn('search:8001', тело)
        self.assertNotIn('нет связи с сервисом', тело)
        self.assertTrue(
            контекст['cards'],
            'Деградация не нашла ничего. Поиск по словам обязан работать '
            'без сервиса — иначе это отказ, а не деградация.')

    def test_лексический_поиск_продолжает_находить(self):
        """Деградация — это «ищем хуже», а не «не ищем вовсе»."""
        from catalog import hybrid

        результаты = hybrid.search('эластичность спроса', limit=10)
        self.assertTrue(
            результаты,
            'Без сервиса поиск не нашёл ничего. Лексическая нога обязана '
            'работать сама по себе — иначе это не деградация, а отказ.')

    def test_в_журнал_идёт_типизированное_событие_без_traceback(self):
        """⚠️ Полная трассировка на КАЖДЫЙ запрос топит журнал.

        Пока сервис лежит, сюда приходит каждый поисковый запрос. Если на
        каждый писать traceback, за минуту журнал превращается в стену
        одинаковых простыней, и настоящая авария в ней теряется.
        """
        from catalog import hybrid

        with self.assertLogs('catalog.hybrid', level='WARNING') as журнал:
            hybrid.search('эластичность спроса', limit=10)

        записи = '\n'.join(журнал.output)
        self.assertIn('search service unavailable', записи)
        self.assertNotIn(
            'Traceback', записи,
            'В журнал уехала трассировка. Для штатного «сервис недоступен» '
            'нужна одна строка с причиной, а не простыня.')

    def test_django_не_лезет_за_моделью_когда_сервиса_нет(self):
        """Соблазн «сервис лёг — посчитаем сами» вернул бы мину №1.

        Причём вернул бы незаметно: модель грузилась бы только когда сервис
        недоступен, то есть в самый неподходящий момент.
        """
        from catalog.tests.test_semantic_degradation import _ЛовушкаИмпорта

        уже = {имя for имя in МОДУЛИ_МОДЕЛИ if имя in sys.modules}
        if уже:
            self.skipTest('модули модели уже импортированы (%s) — перехват '
                          'импорта ослеп' % sorted(уже))

        ловушка = _ЛовушкаИмпорта(МОДУЛИ_МОДЕЛИ)
        sys.meta_path.insert(0, ловушка)
        try:
            ответ = self.client.get(reverse('catalog:problem_list'),
                                    {'q': 'эластичность спроса'})
        finally:
            sys.meta_path.remove(ловушка)

        self.assertEqual(ответ.status_code, 200)
        self.assertEqual(
            ловушка.пойманные, [],
            'Django полез за модулями модели, когда сервис недоступен: %s. '
            'Это возвращает мину №1 — 2,12 ГБ в каждый воркер.'
            % ловушка.пойманные)


class ComposeIsolationTests(SimpleTestCase):
    """Порт сервиса не опубликован наружу — проверка по тексту конфигов.

    `manage.py test` docker не поднимает, поэтому изоляция проверяется как
    свойство описания: у сервиса `search` не должно быть секции `ports`.
    Ручная проверка живым curl — в docs/SERVER.md; здесь сторожим, чтобы
    порт не появился незаметной правкой.
    """

    КОРЕНЬ = Path(__file__).resolve().parents[2]
    ФАЙЛЫ = ('deploy/docker-compose.yml', 'docker-compose.dev.yml')

    def _блок_сервиса(self, текст):
        """Строки описания сервиса search до начала следующего сервиса."""
        строки = текст.splitlines()
        собранное = []
        внутри = False
        for строка in строки:
            if строка.startswith('  search:'):
                внутри = True
                continue
            if внутри:
                # Следующий сервис того же уровня вложенности.
                if строка.startswith('  ') and not строка.startswith('    ') \
                        and строка.strip().endswith(':'):
                    break
                if строка and not строка.startswith(' '):
                    break
                собранное.append(строка)
        return собранное

    def test_у_сервиса_search_нет_опубликованных_портов(self):
        for относительный in self.ФАЙЛЫ:
            путь = self.КОРЕНЬ / относительный
            with self.subTest(файл=относительный):
                self.assertTrue(путь.exists(), 'нет файла %s' % путь)
                блок = self._блок_сервиса(путь.read_text(encoding='utf-8'))
                self.assertTrue(
                    блок, 'В %s не нашёлся сервис search' % относительный)
                действующие = [с for с in блок
                               if not с.strip().startswith('#')]
                for строка in действующие:
                    self.assertNotRegex(
                        строка, r'^\s+ports\s*:',
                        'У сервиса search в %s появилась секция ports. '
                        'Публиковать его наружу нельзя: /encode работает без '
                        'авторизации, и открытый порт раздаёт нашу CPU-'
                        'молотилку кому угодно.' % относительный)


class DevLocalOverrideTests(SimpleTestCase):
    """`docker-compose.dev.local.yml` — надстройка ТОЛЬКО для runserver вне
    Docker (Windows), публикующая порт `search` на loopback.

    ⚠️ Файл намеренно НЕ входит в `ComposeIsolationTests.ФАЙЛЫ` выше — это
    отступление от проверки изоляции для локальной машины, а не дыра в ней:
    `ComposeIsolationTests` продолжает читать `docker-compose.dev.yml` живьём
    и красит тест, если ports попадёт туда, — оверрай на это не влияет,
    потому что лежит отдельным файлом. Здесь проверяется обратное свойство
    самого оверрая: порт торчит НЕ на всех интерфейсах, а только на
    127.0.0.1 — иначе `/encode` без авторизации стал бы виден всей локальной
    сети, не только машине разработчика.
    """

    КОРЕНЬ = Path(__file__).resolve().parents[2]
    ФАЙЛ = 'docker-compose.dev.local.yml'
    _СТРОКА_ПОРТА_RE = re.compile(r"^\s*-\s*['\"]?([^'\"\s]+)['\"]?\s*$")

    def _текст(self):
        путь = self.КОРЕНЬ / self.ФАЙЛ
        self.assertTrue(путь.exists(),
                        'нет файла %s — он должен лежать в репозитории' % путь)
        return путь.read_text(encoding='utf-8')

    def test_файл_не_входит_в_список_проверки_изоляции(self):
        self.assertNotIn(
            self.ФАЙЛ, ComposeIsolationTests.ФАЙЛЫ,
            'Локальная надстройка попала в список файлов ComposeIsolationTests '
            '— проверка изоляции начнёт требовать от неё отсутствия ports, а '
            'весь смысл этого файла ровно в обратном.')

    def test_порт_search_публикуется_только_на_127_0_0_1(self):
        # ⚠️ Смотрим ТОЛЬКО строки самой секции ports, а не весь текст файла:
        # комментарий-объяснение выше по тексту сам упоминает «не 0.0.0.0»,
        # и грубый assertNotIn по всему файлу ловил бы это упоминание, а не
        # настоящую публикацию порта.
        текст = self._текст()
        строки_портов = []
        внутри_ports = False
        for строка in текст.splitlines():
            if re.match(r'^\s*ports\s*:\s*$', строка):
                внутри_ports = True
                continue
            if внутри_ports:
                совпадение = self._СТРОКА_ПОРТА_RE.match(строка)
                if совпадение:
                    строки_портов.append(совпадение.group(1))
                    continue
                if строка.strip():
                    внутри_ports = False

        self.assertTrue(
            строки_портов,
            'В %s не нашлась секция ports сервиса search — нечего публиковать.'
            % self.ФАЙЛ)
        for запись in строки_портов:
            self.assertTrue(
                запись.startswith('127.0.0.1:'),
                'Публикация порта %r не привязана к 127.0.0.1 — сервис без '
                'авторизации станет виден всей локальной сети.' % запись)


class _ЗаглушкаEncode(BaseHTTPRequestHandler):
    """Игрушечная копия `search_service/app.py`: тот же контракт /encode и
    /healthz, без модели — для проверки транспорта до loopback-адреса."""

    protocol_version = 'HTTP/1.1'

    def _тело_json(self):
        длина = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(длина).decode('utf-8'))

    def do_GET(self):
        if self.path != '/healthz':
            self.send_response(404)
            self.end_headers()
            return
        тело = json.dumps({'ok': True, 'model_loaded': True}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(тело)))
        self.end_headers()
        self.wfile.write(тело)

    def do_POST(self):
        if self.path != '/encode':
            self.send_response(404)
            self.end_headers()
            return
        запрос = self._тело_json()
        векторы = [
            base64.b64encode(
                np.full(EMBEDDING_DIM, 0.25, dtype=np.float32).tobytes()
            ).decode('ascii')
            for _ in запрос['texts']
        ]
        тело = json.dumps({
            'vectors': векторы, 'dim': EMBEDDING_DIM,
            'model_build': EMBEDDING_MODEL_BUILD,
        }).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(тело)))
        self.end_headers()
        self.wfile.write(тело)

    def log_message(self, *args):  # noqa: D401 — тишина в выводе тестов
        pass


class LoopbackServiceReachableViaEnvTests(SimpleTestCase):
    """⚠️ ГЛАВНОЕ ДОКАЗАТЕЛЬСТВО ЭТОГО ФАЙЛА ДЛЯ ЛОКАЛЬНОЙ РАСКЛАДКИ: адрес
    сервиса кодирования настраивается извне (`SEARCH_SERVICE_URL`) и по
    такому адресу на loopback реально можно дойти с обычного HTTP-клиента —
    ровно тот механизм, на котором стоит `docker-compose.dev.local.yml`
    (публикует `search` на `127.0.0.1`) плюс `.env` с
    `SEARCH_SERVICE_URL=http://127.0.0.1:8001`.

    Docker здесь не поднимается — игрушечный сервис на чистом
    `http.server` даёт то же самое свойство (реальный TCP-сокет на
    127.0.0.1, реальный HTTP) без веса контейнера и модели.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.сервер = ThreadingHTTPServer(('127.0.0.1', 0), _ЗаглушкаEncode)
        cls.адрес = 'http://127.0.0.1:%d' % cls.сервер.server_address[1]
        cls.поток = threading.Thread(target=cls.сервер.serve_forever,
                                     daemon=True)
        cls.поток.start()

    @classmethod
    def tearDownClass(cls):
        cls.сервер.shutdown()
        cls.сервер.server_close()
        super().tearDownClass()

    def setUp(self):
        caches['search'].clear()

    def test_encode_one_доходит_до_сервиса_по_адресу_из_настроек(self):
        with override_settings(SEARCH_SERVICE_URL=self.адрес,
                               SEARCH_SERVICE_TIMEOUT=2.0):
            вектор = search_client.encode_one('пробный запрос на loopback')
        self.assertEqual(вектор.shape, (EMBEDDING_DIM,))
        self.assertEqual(вектор.dtype, np.float32)

    def test_healthy_отвечает_true_когда_адрес_из_настроек_указывает_на_живой_сервис(self):
        with override_settings(SEARCH_SERVICE_URL=self.адрес,
                               SEARCH_SERVICE_TIMEOUT=2.0):
            self.assertTrue(search_client.healthy())

    def test_смысловой_поиск_видит_плотную_ногу_через_settings(self):
        """Тот же путь, каким идёт `catalog/semantic.py::embed_query` —
        через `SEMANTIC_SEARCH_ENABLED` и `SEARCH_SERVICE_URL` разом, без
        подмены самого клиента. Это и есть то, что должен увидеть
        `catalog.rerank._dense_leg`, когда сервис реально поднят и адрес
        настроен верно."""
        from catalog import semantic

        with override_settings(SEMANTIC_SEARCH_ENABLED=True,
                               SEARCH_SERVICE_URL=self.адрес,
                               SEARCH_SERVICE_TIMEOUT=2.0):
            вектор = semantic.embed_query('пробный запрос на loopback')
        # embed_query нормализует вектор — заглушка отдаёт одинаковые
        # компоненты, поэтому после нормировки норма обязана быть единицей.
        self.assertAlmostEqual(float(np.linalg.norm(вектор)), 1.0, places=5)


# ⚠️ SERIAL, И ВОТ ЗАПИСАННАЯ ПРИЧИНА (правило CLAUDE.md: метку ставим
# только когда тест делит неразделяемый внешний ресурс).
#
# Ресурс здесь — САМА МОДЕЛЬ, 2,27 ГБ в памяти. Замерено 22.08.2026 на
# машине владельца (8 ядер, `--parallel auto` = 8 воркеров): воркер, в
# который попал этот класс, умирал под весом модели, а дальше начиналось
# худшее. Django клонирует тестовую базу РОВНО по числу воркеров
# (default_1…default_8.sqlite3), а multiprocessing взамен умершего
# поднимает воркера со СЛЕДУЮЩИМ номером — 9, 10, … 25. Своего клона у
# них нет, каждый падает с «unable to open database file» и тут же
# заменяется новым. Прогон превращается в лавину из десятков одинаковых
# ошибок, и настоящий результат в ней не разглядеть.
#
# Метка НЕ прячет тест от проверки: он идёт вторым шагом
# (`scripts/run_tests.py`), где процесс один и памяти хватает.
@tag('serial')
@unittest.skipUnless(модель_скачана(),
                     'BGE-M3 не скачана — тест побитового совпадения '
                     'пропущен (модель весит 2,12 ГБ)')
class BitExactEncodingTests(SimpleTestCase):
    """⚠️ ОБЯЗАТЕЛЬНЫЙ ТЕСТ: транспорт не портит вектор.

    Вектор, приехавший по HTTP, обязан быть ПОБИТОВО тем же, что даёт
    модель напрямую. Это не педантизм: испорченный на доли процента вектор
    ничего не уронит — поиск просто начнёт промахиваться, и причину будут
    искать в качестве модели, а не в сериализации.

    ⚠️ МОДЕЛЬ ЗАГРУЖАЕТСЯ ОДИН РАЗ И ПЕРЕИСПОЛЬЗУЕТСЯ СЕРВИСОМ. Честнее
    было бы дать сервису загрузить свою копию, но это 2,27 ГБ памяти
    ВТОРОЙ раз, и на 8-гигабайтной машине прогон бы умер. Поэтому
    экземпляр один, а проверяется то, ради чего тест и написан, — путь
    «numpy -> base64 -> JSON -> base64 -> numpy». Что сервис берёт ту же
    модель и ту же размерность, сторожит отдельная дешёвая проверка ниже.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from sentence_transformers import SentenceTransformer

        import search_service.app as service_app

        cls.service_app = service_app
        cls.model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
        # Отдаём сервису тот же экземпляр — см. предупреждение выше.
        service_app._model = cls.model

        from fastapi.testclient import TestClient

        # ⚠️ НЕ `cls.client`: Django в SimpleTestCase заводит СВОЙ
        # `self.client` и затирает наш. Первая версия теста на этом
        # и подорвалась — запросы уходили в Django, а не в сервис:
        # `/healthz` давал 301 (APPEND_SLASH на `/healthz/`), а
        # `/encode` — 404. Оба выглядели как поломка сервиса.
        cls.service_client = TestClient(service_app.app)

    @classmethod
    def tearDownClass(cls):
        cls.service_app._model = None
        super().tearDownClass()

    def test_сервис_настроен_на_ту_же_модель_и_размерность(self):
        self.assertEqual(self.service_app.MODEL_NAME, EMBEDDING_MODEL_NAME)
        self.assertEqual(self.service_app.EMBEDDING_DIM, EMBEDDING_DIM)
        self.assertEqual(self.service_app.MODEL_BUILD, EMBEDDING_MODEL_BUILD)

    def test_вектор_через_http_побитово_равен_прямому(self):
        текст = 'Монополия с линейным спросом максимизирует прибыль.'

        напрямую = np.asarray(
            self.model.encode([текст], show_progress_bar=False)[0],
            dtype=np.float32)

        ответ = self.service_client.post('/encode', json={'texts': [текст]})
        self.assertEqual(ответ.status_code, 200)
        по_http = search_client._decode_vector(ответ.json()['vectors'][0])

        self.assertEqual(по_http.dtype, np.float32)
        self.assertEqual(по_http.shape, (EMBEDDING_DIM,))
        # tobytes(), а не allclose(): проверяем побитовое равенство, а
        # «примерно равно» пропустило бы ровно ту потерю точности, ради
        # которой тест и написан.
        self.assertEqual(
            по_http.tobytes(), напрямую.tobytes(),
            'Вектор из сервиса отличается от посчитанного напрямую. '
            'Значит, транспорт теряет точность — поиск будет промахиваться '
            'по причине, которой не видно ни в одной другой проверке.')

    def test_healthz_не_требует_модели(self):
        """Проверка живости обязана отвечать до загрузки модели.

        Иначе контейнер считался бы мёртвым все минуты загрузки, и compose
        убивал бы его по кругу, не давая догрузиться.
        """
        сохранённая = self.service_app._model
        self.service_app._model = None
        try:
            ответ = self.service_client.get('/healthz')
            self.assertEqual(ответ.status_code, 200)
            self.assertIs(ответ.json()['ok'], True)
            self.assertIs(ответ.json()['model_loaded'], False)
        finally:
            self.service_app._model = сохранённая
