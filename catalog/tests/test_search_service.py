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
import os
import sys
import unittest
import urllib.request
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
    """Лежит ли BGE-M3 в кэше HuggingFace.

    Проверяем наличие файлов, а не пробуем загрузить: загрузка занимает
    минуты и 2,27 ГБ памяти, и делать это ради `skipUnless` нельзя.
    """
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
                   SEARCH_SERVICE_TIMEOUT=0.5)
class ServiceUnavailableTests(SimpleTestCase):
    """Отказ сервиса поднимает типизированное исключение, а не что попало."""

    def setUp(self):
        caches['search'].clear()

    def test_отказ_соединения_даёт_типизированное_исключение(self):
        with self.assertRaises(search_client.SearchServiceUnavailable):
            search_client.encode_one('эластичность спроса')

    def test_healthy_отвечает_false_а_не_падает(self):
        self.assertFalse(search_client.healthy())


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
        ответ = self.client.get(reverse('catalog:smart_search'),
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
        ответ = self.client.get(reverse('catalog:smart_search'),
                                {'q': 'эластичность спроса'})
        контекст = ответ.context

        self.assertTrue(
            контекст['degraded'],
            'Флаг degraded не выставлен: человеку не сказали, что ищем '
            'только по словам.')
        self.assertIsNone(
            контекст['error'],
            'На экран уехала строка ошибки «%s». Лежащий сервис — это не '
            'ошибка человека, и адрес внутреннего сервиса ему не нужен.'
            % контекст['error'])
        self.assertTrue(
            контекст['results'],
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
            ответ = self.client.get(reverse('catalog:smart_search'),
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
