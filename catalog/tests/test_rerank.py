# -*- coding: utf-8 -*-
"""Тесты `catalog/rerank.py` — переранжирование умного поиска моделью.

⚠️ НИ ОДИН ТЕСТ НЕ ИМПОРТИРУЕТ `bm25s`/`openai` ПО-НАСТОЯЩЕМУ. Ни тот, ни
другой пакет не входят в `requirements/dev.txt` (джоб `tests` в CI ставит
именно его — см. предупреждение про `pymorphy3`/`rapidfuzz` в
`requirements/dev.in`, та же ловушка). Провайдер и корпус подменяются на
швах `catalog.rerank._get_provider` / `catalog.rerank.build_pool` /
`catalog.rerank.get_corpus` — тем же приёмом, каким `FakeProvider`
подменяет реального поставщика в `problems/ai` (см. `problems/ai/CLAUDE.md`,
раздел «Подставной поставщик»): сменяемость должна быть проверяемой, а не
обещанной.
"""
import json
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog import rerank
from problems.tests.factories import make_user


class _FakeReply(object):
    # ⚠️ `cache_write_tokens` появился в двойнике 13.09.2026, когда вызов
    # пошёл через `problems.ai.core.run`: общий учёт считает деньги по
    # ЧЕТЫР�ём счётчикам токенов, и двойник обязан отвечать на все, иначе
    # он проверяет не тот путь, которым идёт боевой код.
    def __init__(self, text, input_tokens=100, output_tokens=50):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.reasoning_tokens = 0


class _FakeProvider(object):
    """Подмена `GLMProvider`: без сети, без ключа, без пакета `openai`."""

    #: Имя поставщика пишется в строку расхода — у настоящего оно есть.
    name = 'glm'

    def __init__(self, script, available=True):
        self._script = script
        self._available = available

    def is_available(self):
        return self._available

    def unavailable_reason(self):
        return '' if self._available else 'подставной поставщик недоступен'

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                timeout=None, images=None):
        return self._script(system_blocks, user_text, schema, model,
                            max_tokens, timeout)


def _usage(batches=1, cost=0.0):
    """Расход одной сборки пула — форма, которую отдаёт `_score_pool`."""
    return {'input_tokens': 100, 'output_tokens': 50, 'batches': batches,
            'model_seconds': 0.1, 'cost_usd': cost}


def _row(pid, **extra):
    row = {'id': pid, 'title': 'задача %d' % pid, 'find': '', 'topics': [],
          'tags': [], 'concepts': [], 'problem_type': '', 'difficulty': None,
          'dup_group': None, 'dup_is_best': False}
    row.update(extra)
    return row


class _База(TestCase):
    def setUp(self):
        rerank.clear_cache()
        self.addCleanup(rerank.clear_cache)
        self.сотрудник = make_user('staff_rerank', is_staff=True)
        self.ученик = make_user('student_rerank', is_staff=False)


# ─── Доступ: выключатель ровно один ───────────────────────────────────────
#
# ⚠️ ОГРАНИЧЕНИЯ «ТОЛЬКО СОТРУДНИКАМ» БОЛЬШЕ НЕТ (13.09.2026). Прежде
# `is_available` требовала `is_staff`, и тесты ниже проверяли, что ученик и
# гость идут прежним путём даже при включённом флаге. Теперь выключатель
# один — `SMART_SEARCH_RERANK`, — и тесты проверяют ровно это: при
# включённом флаге сортировку получают ВСЕ, при выключенном — никто.

class ДоступТесты(_База):
    @override_settings(SMART_SEARCH_RERANK=True)
    def test_ученик_получает_сортировку(self):
        self.assertTrue(rerank.is_available(self.ученик))

    @override_settings(SMART_SEARCH_RERANK=True)
    def test_гость_тоже_получает_сортировку(self):
        """Поиском в каталоге пользуются не входя — ради них и делалось."""
        self.assertTrue(rerank.is_available(AnonymousUser()))
        with mock.patch.object(rerank, 'build_pool',
                               return_value=([1, 2], {'bm25': 2}, {})),              mock.patch.object(rerank, '_score_pool',
                               return_value=([2, 1], _usage(), {})):
            pool_order, status = rerank.apply(AnonymousUser(), 'монополия')
        self.assertEqual(status, 'rerank')
        self.assertEqual(pool_order, [2, 1])

    @override_settings(SMART_SEARCH_RERANK=False)
    def test_флаг_выключен_старый_путь_даже_для_сотрудника(self):
        pool_order, status = rerank.apply(self.сотрудник, 'монополия')
        self.assertIsNone(pool_order)
        self.assertEqual(status, 'off')

    @override_settings(SMART_SEARCH_RERANK=False)
    def test_флаг_выключен_старый_путь_и_для_гостя(self):
        pool_order, status = rerank.apply(AnonymousUser(), 'монополия')
        self.assertIsNone(pool_order)
        self.assertEqual(status, 'off')

    def test_флаг_выключен_по_умолчанию(self):
        self.assertFalse(rerank.is_enabled())


class ИнтеграцияСВьюТесты(_База):
    """Заголовок `X-Smart-Search` и байт-в-байт поведение при выключенном
    флаге — `catalog/views.py` не тронут за пределами этого заголовка."""

    def test_флаг_выключен_заголовок_off(self):
        response = self.client.get(reverse('catalog:problem_list'),
                                   {'q': 'монополия'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Smart-Search'], 'off')

    @override_settings(SMART_SEARCH_RERANK=True)
    def test_флаг_включен_сотрудник_переставляет_порядок(self):
        from problems.tests.factories import make_problem, make_topic

        topic = make_topic('Монополия и рыночная власть')
        p1 = make_problem(statement='Монополист выбирает объём.', topic=topic)
        p2 = make_problem(statement='Монополист сравнивает две цены.',
                          topic=topic)

        def script(system_blocks, user_text, schema, model, max_tokens, timeout):
            return _FakeReply(json.dumps(
                {'rows': [{'id': p1.pk, 'score': 10},
                         {'id': p2.pk, 'score': 95}]}))

        with mock.patch.object(
                rerank, 'build_pool',
                return_value=([p1.pk, p2.pk], {'dense': 2},
                             {p1.pk: _row(p1.pk), p2.pk: _row(p2.pk)})), \
            mock.patch.object(rerank, '_get_provider',
                              return_value=_FakeProvider(script)):
            self.client.force_login(self.сотрудник)
            response = self.client.get(reverse('catalog:problem_list'),
                                       {'q': 'монополия'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Smart-Search'], 'rerank')


# ─── Сборка пула: объединение ног, дедуп-группы, отключённая нога ────────

class СборкаПулаТесты(_База):
    def test_объединение_и_дедуп_групп(self):
        rows = {
            1: _row(1),
            2: _row(2, dup_group='g1', dup_is_best=True),
            3: _row(3, dup_group='g1', dup_is_best=False),
            4: _row(4),
        }
        with mock.patch.object(rerank, 'get_corpus', return_value=(None, rows)), \
            mock.patch.object(rerank, '_dense_leg', return_value=[1, 2]), \
            mock.patch.object(rerank, '_bm25_leg', return_value=[3, 4]), \
            override_settings(
                SMART_SEARCH_RERANK_LEGS=frozenset({'dense', 'bm25'}),
                SMART_SEARCH_RERANK_POOL_CAP=150):
            pool_ids, leg_sizes, out_rows = rerank.build_pool('монополия')
        # 3 — дубль 2 (одна группа g1, 2 — фаворит): убран из пула.
        self.assertEqual(pool_ids, [1, 2, 4])
        self.assertEqual(leg_sizes, {'dense': 2, 'bm25': 2})
        self.assertIs(out_rows, rows)

    def test_отключённая_нога_не_участвует(self):
        with mock.patch.object(rerank, 'get_corpus', return_value=(None, {})), \
            mock.patch.object(rerank, '_dense_leg', return_value=[1, 2]), \
            mock.patch.object(rerank, '_bm25_leg') as bm25_leg, \
            override_settings(SMART_SEARCH_RERANK_LEGS=frozenset({'dense'})):
            pool_ids, leg_sizes, _rows = rerank.build_pool('монополия')
        self.assertEqual(pool_ids, [1, 2])
        self.assertNotIn('bm25', leg_sizes)
        bm25_leg.assert_not_called()

    def test_потолок_пула_срезает_хвост(self):
        rows = {i: _row(i) for i in range(1, 6)}
        with mock.patch.object(rerank, 'get_corpus', return_value=(None, rows)), \
            mock.patch.object(rerank, '_dense_leg',
                              return_value=[1, 2, 3, 4, 5]), \
            mock.patch.object(rerank, '_bm25_leg', return_value=[]), \
            override_settings(
                SMART_SEARCH_RERANK_LEGS=frozenset({'dense', 'bm25'}),
                SMART_SEARCH_RERANK_POOL_CAP=3):
            pool_ids, _leg_sizes, _rows = rerank.build_pool('монополия')
        self.assertEqual(pool_ids, [1, 2, 3])


# ─── Карточка, промпт, разбор ответа, слияние пачек по баллу ─────────────

class КарточкаИРазборТесты(TestCase):
    def test_merge_слияние_по_баллу_и_хвост_неоценённых(self):
        chunks = [{1: 90, 2: 10}, {3: 50}]
        ranked = rerank.merge(chunks, all_ids=[1, 2, 3, 4])
        self.assertEqual(ranked, [1, 3, 2, 4])

    def test_parse_scores_терпит_лишнее_и_считает_пропуски(self):
        scores, missing, extra = rerank.parse_scores(
            {'1': 80, '99': 10, 'x': 'плохо'}, [1, 2])
        self.assertEqual(scores, {1: 80})
        self.assertEqual(missing, [2])
        self.assertIn('99', extra)

    def test_parse_json_object_терпит_массив_вместо_объекта(self):
        text = '[{"id": 1, "score": 70}, {"id": 2, "score": 30}]'
        self.assertEqual(rerank.parse_json_object(text), {'1': 70, '2': 30})

    def test_parse_json_object_терпит_markdown_обрамление(self):
        text = '```json\n{"rows": [{"id": 1, "score": 55}]}\n```'
        self.assertEqual(rerank.parse_json_object(text), {'1': 55})

    def test_parse_json_object_терпит_обрезанный_json(self):
        # Пачка оборвалась на втором кандидате — закрывающей ']' нет.
        text = '[{"id": 1, "score": 80}, {"id": 2, "score": 40}'
        self.assertEqual(rerank.parse_json_object(text), {'1': 80})

    def test_card_не_содержит_условие(self):
        text = rerank.card(_row(1, title='Заголовок', find='найти прибыль'))
        self.assertIn('найти: найти прибыль', text)
        self.assertNotIn('условие', text.lower())

    def test_collapse_dedup_оставляет_фаворита(self):
        groups = {1: ('g', False), 2: ('g', True)}
        kept, dropped = rerank.collapse_dedup([1, 2], groups)
        self.assertEqual(kept, [2])
        self.assertEqual(dropped, [{'id': 1, 'group': 'g', 'kept': 2}])


# ─── Отказоустойчивость: таймаут, нечитаемый ответ, пустой пул ───────────

class ОтказоустойчивостьТесты(_База):
    def test_пустой_пул_дает_базовый_порядок(self):
        with mock.patch.object(rerank, 'build_pool',
                               return_value=([], {}, {})):
            result = rerank._run('нечто несуществующее')
        self.assertEqual(result.status, 'fallback')
        self.assertEqual(result.reason, 'пустой пул')

    def test_таймаут_дает_базовый_порядок_и_причину(self):
        with mock.patch.object(rerank, 'build_pool',
                               return_value=([1, 2], {'dense': 2}, {})), \
            mock.patch.object(rerank, '_score_pool',
                              side_effect=TimeoutError('не все пачки ответили')):
            result = rerank._run('монополия')
        self.assertEqual(result.status, 'fallback')
        self.assertIn('TimeoutError', result.reason)

    def test_нечитаемый_ответ_дает_базовый_порядок(self):
        provider = _FakeProvider(
            lambda *a, **k: _FakeReply('это совсем не json'))
        with mock.patch.object(
                rerank, 'build_pool',
                return_value=([1], {'dense': 1}, {1: _row(1)})), \
            mock.patch.object(rerank, '_get_provider', return_value=provider):
            result = rerank._run('монополия')
        self.assertEqual(result.status, 'fallback')

    def test_поставщик_недоступен_дает_базовый_порядок(self):
        provider = _FakeProvider(lambda *a, **k: _FakeReply('{}'),
                                 available=False)
        with mock.patch.object(
                rerank, 'build_pool',
                return_value=([1], {'dense': 1}, {1: _row(1)})), \
            mock.patch.object(rerank, '_get_provider', return_value=provider):
            result = rerank._run('монополия')
        self.assertEqual(result.status, 'fallback')
        self.assertIn('недоступен', result.reason)

    def test_успешное_переранжирование(self):
        rows = {1: _row(1), 2: _row(2), 3: _row(3)}

        def script(system_blocks, user_text, schema, model, max_tokens, timeout):
            return _FakeReply(json.dumps(
                {'rows': [{'id': 1, 'score': 10}, {'id': 2, 'score': 90},
                         {'id': 3, 'score': 50}]}))

        with mock.patch.object(
                rerank, 'build_pool',
                return_value=([1, 2, 3], {'dense': 3}, rows)), \
            mock.patch.object(rerank, '_get_provider',
                              return_value=_FakeProvider(script)):
            result = rerank._run('монополия')
        self.assertEqual(result.status, 'rerank')
        self.assertEqual(result.ids, [2, 3, 1])
        self.assertEqual(result.batches, 1)

    def test_несколько_пачек_сливаются_по_баллу(self):
        rows = {i: _row(i) for i in (1, 2, 3, 4)}

        def script(system_blocks, user_text, schema, model, max_tokens, timeout):
            ids_in_chunk = [int(line.split(': ')[1])
                            for line in user_text.splitlines()
                            if line.startswith('id: ')]
            return _FakeReply(json.dumps(
                {'rows': [{'id': pid, 'score': pid * 10}
                         for pid in ids_in_chunk]}))

        with mock.patch.object(
                rerank, 'build_pool',
                return_value=([1, 2, 3, 4], {'dense': 4}, rows)), \
            mock.patch.object(rerank, '_get_provider',
                              return_value=_FakeProvider(script)), \
            override_settings(SMART_SEARCH_RERANK_BATCH_SIZE=2):
            result = rerank._run('запрос')
        self.assertEqual(result.status, 'rerank')
        self.assertEqual(result.ids, [4, 3, 2, 1])
        self.assertEqual(result.batches, 2)


# ─── Общая дверь наружу и денежный потолок ────────────────────────────────

class ОбщаяДверьТесты(_База):
    """Вызов идёт через `problems.ai.core.run` — с учётом и с потолком."""

    def _прогнать(self, запрос='монополия'):
        rows = {1: _row(1), 2: _row(2)}

        def script(system_blocks, user_text, schema, model, max_tokens, timeout):
            return _FakeReply(json.dumps(
                {'rows': [{'id': 1, 'score': 10}, {'id': 2, 'score': 90}]}))

        with mock.patch.object(
                rerank, 'build_pool',
                return_value=([1, 2], {'bm25': 2}, rows)),             mock.patch.object(rerank, '_get_provider',
                              return_value=_FakeProvider(script)):
            return rerank._run(запрос)

    def test_расход_попадает_в_общий_журнал(self):
        """Строка `AiUsageLog` пишется, и пишется БЕЗ пользователя.

        Поиском пользуются не входя; до 13.09.2026 такие строки не
        писались вовсе, и денежный потолок считать было не по чему.
        """
        from problems.models import AiUsageLog

        self.assertEqual(AiUsageLog.objects.count(), 0)
        result = self._прогнать()
        self.assertEqual(result.status, 'rerank')
        row = AiUsageLog.objects.get()
        self.assertEqual(row.kind, rerank.USAGE_KIND)
        self.assertIsNone(row.user)
        self.assertEqual(row.provider, 'glm')
        self.assertGreater(row.cost_usd, 0)

    def test_цена_считается_общей_таблицей_настроек(self):
        """Своей таблицы цен у модуля нет — цена берётся из AI_PRICES."""
        with override_settings(SMART_SEARCH_RERANK_MODEL='glm-5.3-flash'):
            result = self._прогнать()
        # 100 токенов входа по $0,15/млн + 50 выхода по $0,50/млн.
        self.assertAlmostEqual(result.cost_usd, (100 * 0.15 + 50 * 0.50) / 1e6,
                               places=9)

    @override_settings(AI_DAILY_COST_CAPS={'search_rerank': 0.0000001})
    def test_исчерпанный_бюджет_тихо_уводит_на_базовый_порядок(self):
        """Потолок выбран — выдача та же, что без сортировщика вовсе."""
        first = self._прогнать('первый запрос')
        self.assertEqual(first.status, 'rerank')
        second = self._прогнать('второй запрос')
        self.assertEqual(second.status, 'fallback')
        self.assertIn('бюджет', second.reason)
        self.assertEqual(second.ids, [])     # «ничего не менять»

    @override_settings(AI_DAILY_COST_CAPS={})
    def test_без_потолка_ограничения_нет(self):
        self._прогнать('первый запрос')
        self.assertEqual(self._прогнать('второй запрос').status, 'rerank')

    def test_суточный_лимит_обращений_на_пользователя_не_применяется(self):
        """У поиска нет пользователя, которому списывать обращения."""
        with override_settings(AI_GENERATOR_DAILY_LIMIT=0):
            self.assertEqual(self._прогнать().status, 'rerank')


# ─── Кэш: час по нормализованному тексту запроса ──────────────────────────

class КэшТесты(_База):
    def test_кэш_отдает_сохраненный_результат(self):
        calls = []

        def fake_run(query):
            calls.append(query)
            return rerank.RerankResult([1, 2], 'rerank')

        with mock.patch.object(rerank, '_run', side_effect=fake_run):
            first = rerank.rerank('Монополия')
            second = rerank.rerank('  монополия  ')
        self.assertEqual(len(calls), 1)
        self.assertEqual(first.ids, second.ids)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)

    def test_разные_запросы_не_делят_кэш(self):
        calls = []

        def fake_run(query):
            calls.append(query)
            return rerank.RerankResult([1], 'rerank')

        with mock.patch.object(rerank, '_run', side_effect=fake_run):
            rerank.rerank('монополия')
            rerank.rerank('олигополия')
        self.assertEqual(len(calls), 2)


# ─── Лог: строка содержит все поля ─────────────────────────────────────────

class ЛогТесты(TestCase):
    def test_строка_лога_содержит_все_поля(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, 'smart_search_log.jsonl')
            result = rerank.RerankResult(
                [1, 2], 'rerank', leg_sizes={'dense': 2, 'bm25': 1},
                batches=1, model_seconds=1.2, total_seconds=1.5,
                cost_usd=0.0012)
            with mock.patch.object(rerank, '_log_path',
                                   return_value=log_path):
                rerank._log('монополия', result)
            with open(log_path, encoding='utf-8') as handle:
                row = json.loads(handle.readline())
        for field in ('ts', 'query', 'pool_by_leg', 'batches',
                     'model_seconds', 'total_seconds', 'cost_usd', 'outcome',
                     'cache_hit'):
            self.assertIn(field, row)
        self.assertEqual(row['outcome'], 'rerank')
        self.assertEqual(row['query'], 'монополия')

    def test_строка_лога_фолбэка_называет_причину(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, 'smart_search_log.jsonl')
            result = rerank.RerankResult([], 'fallback', reason='пустой пул')
            with mock.patch.object(rerank, '_log_path',
                                   return_value=log_path):
                rerank._log('абракадабра', result)
            with open(log_path, encoding='utf-8') as handle:
                row = json.loads(handle.readline())
        self.assertEqual(row['outcome'], 'fallback: пустой пул')
