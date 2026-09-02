# -*- coding: utf-8 -*-
"""glm_enrich_run — боевая команда (Фазы 3-5). Смок-тест на всю команду
целиком с подставным провайдером — реальная сеть проверяется живым
прогоном, не тестом; здесь проверяем, что конвейер (журнал → parsed →
metrics) не падает и даёт ожидаемую форму."""
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from problems.ai import providers
from problems.enrich import taxonomy
from problems.management.commands import glm_enrich_run as run_cmd
from problems.models import Problem, Source, SourceReference


def _valid_call1_json(theme_idx=0):
    theme_id = taxonomy.theme_ids()[theme_idx]
    tag_id = taxonomy.tag_ids()[theme_idx]
    return json.dumps({
        'topic_primary': theme_id, 'topics_secondary': [], 'tags': [tag_id],
        'given': 'Линейная функция спроса', 'find': 'Точку равновесия',
        'econ_concepts': ['спрос', 'предложение', 'равновесие'],
        'concepts_offlist': [], 'task_nature': 'расчётная',
        'features_1': [], 'topic_confidence': 'высокая',
    }, ensure_ascii=False)


VALID_CALL2_JSON = json.dumps({
    # §12 правило 3: без цифр — это не опечатка, это ровно то, что теперь
    # проверяет validate_call2().
    'search_queries': ['запрос номер ' + w for w in
                       ('один', 'два', 'три', 'четыре', 'пять', 'шесть',
                        'семь', 'восемь')],
    'text_quality': 'чистая', 'text_quality_note': '',
    'problem_type': 'открытый_ответ', 'difficulty': 2,
    'difficulty_note': 'просто', 'answer_consistency': 'согласован',
    'plot': None, 'hints': None, 'title_candidate': 'Рынок кофе',
}, ensure_ascii=False)

INVALID_CALL1_JSON = '{"topic_primary": "999", "given": "P=10"}'


class _FakeReply:
    def __init__(self, text, input_tokens=100, output_tokens=50,
                cache_write_tokens=0, cache_read_tokens=9800, reasoning_tokens=0):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_write_tokens = cache_write_tokens
        self.cache_read_tokens = cache_read_tokens
        self.reasoning_tokens = reasoning_tokens


@override_settings(AI_PRICES={run_cmd.GLM_MODEL: run_cmd.GLM_PRICES_PROMO})
class GlmEnrichRunSmokeTests(TestCase):

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.problems = [
            Problem.objects.create(statement='Задача %d про рынок.' % i)
            for i in range(6)
        ]
        # исключаем служебные фикстуры из выборки — проверяем, что и
        # обычные, непривязанные к источнику задачи (как здесь) остаются.
        self.raw_path = self.tmp_dir / 'run_raw.jsonl'
        self.parsed_path = self.tmp_dir / 'run_parsed.jsonl'
        self.metrics_path = self.tmp_dir / 'run_metrics.json'

    def _patch_paths(self):
        return mock.patch.multiple(
            run_cmd,
            RAW_LOG_PATH=self.raw_path,
            PARSED_LOG_PATH=self.parsed_path,
            METRICS_PATH=self.metrics_path,
        )

    def test_полный_прогон_без_брака_создаёт_три_файла(self):
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json() if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='test-run-1')

        self.assertTrue(self.raw_path.exists())
        self.assertTrue(self.parsed_path.exists())
        self.assertTrue(self.metrics_path.exists())

        raw_lines = self.raw_path.read_text(encoding='utf-8').strip().splitlines()
        self.assertEqual(len(raw_lines), len(self.problems) * 2)  # 6×(call1+call2)
        for line in raw_lines:
            json.loads(line)  # каждая строка — валидный JSON

        parsed_lines = self.parsed_path.read_text(encoding='utf-8').strip().splitlines()
        self.assertEqual(len(parsed_lines), len(self.problems))
        parsed = [json.loads(line) for line in parsed_lines]
        self.assertTrue(all(not p['defect'] for p in parsed))

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['total_processed'], len(self.problems))
        self.assertEqual(metrics['defects'], 0)

    def test_невалидный_ответ_после_повтора_считается_браком(self):
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(INVALID_CALL1_JSON if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='test-run-2')

        parsed = [json.loads(line) for line in
                 self.parsed_path.read_text(encoding='utf-8').strip().splitlines()]
        self.assertTrue(all(p['defect'] for p in parsed))
        self.assertTrue(all(p['call1_retried'] for p in parsed))

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['defects'], len(self.problems))

    def test_резюмирование_не_платит_дважды(self):
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json() if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='same-run-id')

        calls = []

        def counting_complete(model, blocks, user_text, schema, effort, images=None):
            calls.append(model)
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json() if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=counting_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='same-run-id')

        self.assertEqual(len(calls), 0)

    def test_ids_выбирает_конкретные_задачи_и_не_трогает_официальные_файлы(self):
        """Донабор с картинками (решение владельца 02.09.2026) не должен
        затирать run_parsed.jsonl/run_metrics.json официального чек-поинта
        «первые 300» — только свой --parsed-out/--metrics-out."""
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json() if is_call1 else VALID_CALL2_JSON)

        chosen_ids = [self.problems[1].id, self.problems[3].id]
        supplement_parsed = self.tmp_dir / 'supplement_parsed.jsonl'
        supplement_metrics = self.tmp_dir / 'supplement_metrics.json'

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', ids=','.join(map(str, chosen_ids)),
                        max_cost=100.0, workers=2, run_id='supplement-run',
                        parsed_out=str(supplement_parsed),
                        metrics_out=str(supplement_metrics))

        self.assertFalse(self.parsed_path.exists())
        self.assertFalse(self.metrics_path.exists())
        self.assertTrue(supplement_parsed.exists())
        parsed = [json.loads(line) for line in
                 supplement_parsed.read_text(encoding='utf-8').strip().splitlines()]
        self.assertEqual(sorted(p['problem_id'] for p in parsed), sorted(chosen_ids))

    def test_фикстуры_рендерера_исключены_из_выборки(self):
        fixture_source = Source.objects.create(name=run_cmd.SERVICE_FIXTURE_SOURCE)
        fixture_problem = Problem.objects.create(statement='Служебная фикстура.')
        SourceReference.objects.create(problem=fixture_problem, source=fixture_source)

        ids = list(run_cmd.battle_queryset().values_list('id', flat=True))
        self.assertNotIn(fixture_problem.id, ids)
        self.assertTrue(all(p.id in ids for p in self.problems))


class GlmEnrichRunPricesRegressionTests(TestCase):
    """Регресс на баг боевого чек-поинта 02.09.2026: команда сама
    оборачивает `AI_PRICES` для GLM через `override_settings` (Фаза 3.3
    внутри неё же нуждается в цене модели для подсчёта метрик) — этот
    класс НАРОЧНО без class-level `override_settings`, иначе баг снова
    спрятался бы за настройкой теста, а не за собственным кодом команды
    (именно так он и остался незамеченным до живого прогона)."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.problems = [Problem.objects.create(statement='Задача %d.' % i)
                         for i in range(3)]
        self.raw_path = self.tmp_dir / 'run_raw.jsonl'
        self.parsed_path = self.tmp_dir / 'run_parsed.jsonl'
        self.metrics_path = self.tmp_dir / 'run_metrics.json'

    def test_метрики_считаются_без_внешнего_ai_prices(self):
        from django.conf import settings
        self.assertNotIn(run_cmd.GLM_MODEL, getattr(settings, 'AI_PRICES', {}))

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json() if is_call1 else VALID_CALL2_JSON)

        with mock.patch.multiple(
                run_cmd, RAW_LOG_PATH=self.raw_path, PARSED_LOG_PATH=self.parsed_path,
                METRICS_PATH=self.metrics_path), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=2, run_id='prices-regression')

        self.assertTrue(self.metrics_path.exists())
        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['total_processed'], len(self.problems))
        self.assertGreater(Decimal(metrics['usage_totals']['cost_usd']), 0)
