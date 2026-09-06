# -*- coding: utf-8 -*-
"""С14 — команда `build_eval_set_b` (обратная генерация запросов).

Прогон идёт на подставном поставщике (`AI_PROVIDER='fake'`): к настоящей
модели тесты не ходят и денег не тратят. Проверяется весь слой целиком —
профиль, схема, разбор ответа, сборка набора.

⚠️ ГЛАВНОЕ ЗДЕСЬ — ТЕСТ НА `--dry-run` ПО УМОЛЧАНИЮ. Команда тратит деньги, и
случайный запуск без флага обязан не сделать ничего. Регламент слоя команд
требует этого от любой массовой команды; здесь цена ошибки прямая, в рублях.
"""
import json
import re
import tempfile
from io import StringIO
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from problems.models import Problem
from problems.tests.factories import make_problem

ОТВЕТ = json.dumps(
    {'queries': ['потоварный налог на монополию',
                 'фирма выбирает выпуск при налоге',
                 'найти ставку, максимизирующую сборы']},
    ensure_ascii=False)


@override_settings(AI_PROVIDER='fake', AI_FAKE_REPLY=ОТВЕТ)
class BuildEvalSetBTests(TestCase):

    def setUp(self):
        # Условие длиннее 200 символов — короткие команда отбрасывает
        # намеренно: на огрызке модель напишет три одинаковые общие фразы.
        for н in range(3):
            p = make_problem(statement=f'Задача номер {н}. ' + 'Текст. ' * 40)
            Problem.objects.filter(pk=p.pk).update(
                status=Problem.Status.PUBLISHED, needs_quality_review=False,
                hidden_pending_review=False, embedding=b'\x00' * 4096)

    def _путь(self, d):
        return str(Path(d) / 'eval_set_b.json')

    def test_без_apply_ничего_не_пишется(self):
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            call_command('build_eval_set_b', limit=3, out=путь, verbosity=0)
            self.assertFalse(Path(путь).exists())

    def test_с_apply_набор_собирается_по_три_запроса_на_задачу(self):
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            call_command('build_eval_set_b', limit=3, out=путь, apply=True,
                         verbosity=0)
            данные = json.loads(Path(путь).read_text(encoding='utf-8'))
        self.assertEqual(данные['count'], 9)
        self.assertEqual(данные['mode'], 'text')

    def test_каждый_запрос_ведёт_на_свою_задачу(self):
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            call_command('build_eval_set_b', limit=3, out=путь, apply=True,
                         verbosity=0)
            данные = json.loads(Path(путь).read_text(encoding='utf-8'))
        ids = {c['relevant_ids'][0] for c in данные['cases']}
        self.assertEqual(ids, set(Problem.objects.values_list('id', flat=True)))

    def test_запрет_на_абсолютные_цифры_записан_в_самом_файле(self):
        # Правило обязано ехать вместе с данными. Лежи оно только в отчёте
        # сессии — через месяц по набору B назовут абсолютное качество поиска,
        # и число будет завышено примерно на 0,2 nDCG@10.
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            call_command('build_eval_set_b', limit=3, out=путь, apply=True,
                         verbosity=0)
            данные = json.loads(Path(путь).read_text(encoding='utf-8'))
        предупреждения = ' '.join(данные['warnings'])
        self.assertIn('ЗАПРЕЩЕНО', предупреждения)
        self.assertIn('РАЗРЕШЕНО', предупреждения)

    def test_выборка_повторяема_при_том_же_зерне(self):
        # Иначе повторный прогон стоил бы денег и дал бы ДРУГОЙ эталон:
        # сравнивать замеры между собой стало бы нельзя.
        наборы = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                путь = self._путь(d)
                call_command('build_eval_set_b', limit=2, out=путь,
                             apply=True, seed=777, verbosity=0)
                данные = json.loads(Path(путь).read_text(encoding='utf-8'))
            наборы.append([c['relevant_ids'] for c in данные['cases']])
        self.assertEqual(наборы[0], наборы[1])

    def test_настоящий_расход_попадает_в_итог(self):
        # ⚠️ ЭТОТ ТЕСТ ЛОВИТ УЖЕ СЛУЧИВШУЮСЯ ОШИБКУ. Первая версия команды
        # читала расход как `итог.usage.cost` через getattr с умолчанием 0.0,
        # а `usage` — это СЛОВАРЬ с ключом `cost_usd`. getattr на словаре
        # всегда возвращал умолчание, и счётчик денег молча показывал ноль:
        # прогон на тысяче задач отчитался бы «потрачено $0.00».
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            вывод = StringIO()
            call_command('build_eval_set_b', limit=3, out=путь, apply=True,
                         stdout=вывод, verbosity=1)
            данные = json.loads(Path(путь).read_text(encoding='utf-8'))
        self.assertGreater(данные['spent_usd'], 0.0)

    def test_прогон_останавливается_при_превышении_бюджета(self):
        # Смета — это оценка, а оценка может ошибиться. Потолок считается по
        # НАСТОЯЩИМ токенам из ответа, поэтому он держит даже тогда, когда
        # смета промахнулась.
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            with self.assertRaises(CommandError) as поймано:
                call_command('build_eval_set_b', limit=3, out=путь,
                             apply=True, max_cost=0.0000001, verbosity=0)
        self.assertIn('бюджет', str(поймано.exception).lower())

    def test_бюджет_не_мешает_когда_его_хватает(self):
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            call_command('build_eval_set_b', limit=3, out=путь, apply=True,
                         max_cost=100.0, verbosity=0)
            данные = json.loads(Path(путь).read_text(encoding='utf-8'))
        self.assertEqual(данные['count'], 9)

    def test_смета_учитывает_кэш_системного_блока(self):
        # Блок CORE помечен cache_control и на повторных обращениях стоит
        # десятую часть цены. Смета, считающая его полным тарифом на каждой
        # из тысячи задач, завышена почти вдвое — а завышенная смета так же
        # мешает принять решение, как и заниженная.
        with tempfile.TemporaryDirectory() as d:
            вывод = StringIO()
            call_command('build_eval_set_b', limit=10, out=self._путь(d),
                         stdout=вывод, verbosity=1)
        текст = вывод.getvalue()
        self.assertIn('кэш', текст.lower())
        # Смета показывает вилку, а не одно число: токенизатор русского
        # текста у модели точно не известен, и делать вид, что известен,
        # нельзя.
        self.assertIn('…', текст.replace('...', '…'))

    def test_команда_не_меняет_защищённые_поля(self):
        поля = ('statement', 'solution', 'answer', 'embedding',
                'content_format', 'human_review')
        до = list(Problem.objects.order_by('id').values('id', *поля))
        with tempfile.TemporaryDirectory() as d:
            call_command('build_eval_set_b', limit=3, out=self._путь(d),
                         apply=True, verbosity=0)
        после = list(Problem.objects.order_by('id').values('id', *поля))
        self.assertEqual(до, после)


# ── Ограничения массивов в JSON-схеме ────────────────────────────────────
#
# ⚠️ ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ БЛОК ТЕСТОВ. Structured output Anthropic
# поддерживает у массива `minItems` только 0 или 1; любое другое значение и
# ЛЮБОЙ `maxItems` — это ошибка 400 на первом же обращении, до генерации:
#
#     output_config.format.schema: For 'array' type, 'minItems' values other
#     than 0 or 1 are not supported (got: [2, 5])
#
# Схема с `minItems: 3, maxItems: 3` ровно так и уронила пилот набора B
# 28.08. Ограничение документировано у Anthropic в разделе «Not supported»
# и на нашей стороне не чинится — количество держат промпт и разбор ответа.

ЗАПРЕЩЁННЫЕ_В_СХЕМЕ = re.compile(
    r"""['"]maxItems['"]|['"]minItems['"]\s*:\s*(?!\s*[01]\s*[,}\]])\s*\d+""")


def _обойти_схему(узел, путь='$'):
    """Все пары (путь, узел-словарь) схемы, включая вложенные."""
    if isinstance(узел, dict):
        yield путь, узел
        for ключ, значение in узел.items():
            yield from _обойти_схему(значение, f'{путь}.{ключ}')
    elif isinstance(узел, list):
        for н, значение in enumerate(узел):
            yield from _обойти_схему(значение, f'{путь}[{н}]')


class ОграниченияМассивовВСхемахTests(SimpleTestCase):

    def test_схема_набора_b_не_ограничивает_длину_массива(self):
        from problems.management.commands.build_eval_set_b import СХЕМА

        for путь, узел in _обойти_схему(СХЕМА):
            self.assertNotIn(
                'maxItems', узел,
                f'{путь}: maxItems не поддерживается structured output')
            if 'minItems' in узел:
                self.assertIn(
                    узел['minItems'], (0, 1),
                    f'{путь}: minItems допускает только 0 или 1, '
                    f'получено {узел["minItems"]!r}')

    def test_все_схемы_слоя_ии_не_ограничивают_длину_массива(self):
        from problems.hw_generator import PLAN_SCHEMA

        for имя, схема in (('PLAN_SCHEMA', PLAN_SCHEMA),):
            for путь, узел in _обойти_схему(схема, имя):
                self.assertNotIn('maxItems', узел, путь)
                if 'minItems' in узел:
                    self.assertIn(узел['minItems'], (0, 1), путь)

    def test_в_исходниках_нет_запрещённых_ограничений_массива(self):
        """Сторож на будущие схемы, о которых этот файл ещё не знает.

        Разбор схем по объектам ловит только те две, что перечислены выше.
        Новая схема в новой команде проскочила бы мимо — и упала бы уже
        деньгами на боевом прогоне. Поэтому вдобавок читаются исходники.
        """
        корень = Path(__file__).resolve().parents[2]
        пакеты = ('problems', 'catalog', 'teacher', 'student', 'game',
                  'calc2', 'config', 'calendar_stub', 'search_service')
        нарушения = []
        for пакет in пакеты:
            for файл in (корень / пакет).rglob('*.py'):
                if 'tests' in файл.parts or '__pycache__' in файл.parts:
                    continue
                текст = файл.read_text(encoding='utf-8', errors='replace')
                for н, строка in enumerate(текст.splitlines(), start=1):
                    if ЗАПРЕЩЁННЫЕ_В_СХЕМЕ.search(строка):
                        нарушения.append(
                            f'{файл.relative_to(корень)}:{н}: {строка.strip()}')
        self.assertEqual(
            нарушения, [],
            'structured output Anthropic не поддерживает эти ограничения:\n'
            + '\n'.join(нарушения))


# ── Количество фраз держит разбор ответа, а не схема ─────────────────────

ОТВЕТ_ДВЕ_ФРАЗЫ = json.dumps(
    {'queries': ['потоварный налог на монополию', 'налог и выпуск фирмы']},
    ensure_ascii=False)

ОТВЕТ_ПЯТЬ_ФРАЗ = json.dumps(
    {'queries': ['раз', 'два', 'три', 'четыре', 'пять']}, ensure_ascii=False)

ОТВЕТ_ПУСТАЯ_СРЕДИ_ТРЁХ = json.dumps(
    {'queries': ['потоварный налог на монополию', '   ', 'ставка сборов']},
    ensure_ascii=False)


@override_settings(AI_PROVIDER='fake')
class ДлинаОтветаNabораBTests(TestCase):
    """Схема больше не может требовать ровно три фразы — требует разбор."""

    def setUp(self):
        # ⚠️ ОБЩИЙ КЭШ ОТВЕТОВ МЕЖДУ ТЕСТАМИ. `core.run` кладёт ответ в кэш
        # Django по ключу (профиль, модель, текст задачи), а LocMemCache живёт
        # весь процесс — база откатывается, кэш нет. Условия здесь у всех
        # тестов одинаковые, поэтому второй тест получил бы ответ первого и
        # мерил бы не свой AI_FAKE_REPLY. Видно это только на тестах с РАЗНЫМИ
        # ответами: пока ответ у всех один, подмена незаметна.
        cache.clear()
        for н in range(3):
            p = make_problem(statement=f'Задача номер {н}. ' + 'Текст. ' * 40)
            Problem.objects.filter(pk=p.pk).update(
                status=Problem.Status.PUBLISHED, needs_quality_review=False,
                hidden_pending_review=False, embedding=b'\x00' * 4096)

    def _собрать(self, ответ):
        with override_settings(AI_FAKE_REPLY=ответ):
            with tempfile.TemporaryDirectory() as d:
                путь = str(Path(d) / 'eval_set_b.json')
                вывод = StringIO()
                call_command('build_eval_set_b', limit=3, out=путь, apply=True,
                             stdout=вывод, verbosity=1)
                return json.loads(Path(путь).read_text(encoding='utf-8'))

    def test_две_фразы_вместо_трёх_это_ошибка_по_задаче(self):
        данные = self._собрать(ОТВЕТ_ДВЕ_ФРАЗЫ)
        self.assertEqual(данные['count'], 0)
        self.assertIn('Ошибок при генерации: 3 из 3',
                      ' '.join(данные['warnings']))

    def test_пять_фраз_вместо_трёх_это_ошибка_по_задаче(self):
        данные = self._собрать(ОТВЕТ_ПЯТЬ_ФРАЗ)
        self.assertEqual(данные['count'], 0)
        self.assertIn('Ошибок при генерации: 3 из 3',
                      ' '.join(данные['warnings']))

    def test_пустая_строка_среди_трёх_это_ошибка_а_не_молчаливый_пропуск(self):
        """Иначе набор тихо недосчитался бы фраз, за которые заплачено."""
        данные = self._собрать(ОТВЕТ_ПУСТАЯ_СРЕДИ_ТРЁХ)
        self.assertEqual(данные['count'], 0)

    def test_ровно_три_фразы_проходят(self):
        данные = self._собрать(ОТВЕТ)
        self.assertEqual(данные['count'], 9)
        self.assertIn('Ошибок при генерации: 0 из 3',
                      ' '.join(данные['warnings']))
