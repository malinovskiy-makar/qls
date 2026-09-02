# -*- coding: utf-8 -*-
"""glm_enrich_run — боевая команда (Фазы 3-5). Смок-тест на всю команду
целиком с подставным провайдером — реальная сеть проверяется живым
прогоном, не тестом; здесь проверяем, что конвейер (журнал → parsed →
metrics) не падает и даёт ожидаемую форму."""
import io
import json
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from problems.ai import providers
from problems.enrich import taxonomy
from problems.management.commands import glm_enrich_run as run_cmd
from problems.models import Problem, ProblemFigure, Source, SourceReference


_SHORTLIST_RE = re.compile(
    r'ШОРТ-ЛИСТ ПОНЯТИЙ ДЛЯ econ_concepts.*?:\n(.*?)\n\nЗАДАЧА', re.DOTALL)


def _shortlist_from_user_text(user_text):
    """Достаёт шорт-лист из готового текста промпта (`call1_user_text`) —
    так фиктивный ответ модели в тестах отвечает econ_concepts, которые
    ДЕЙСТВИТЕЛЬНО из шорт-листа ЭТОЙ задачи (Фаза 1 задания сессии 02.09,
    вторая пересъёмка: «понятие вне шорт-листа» стало жёсткой проверкой в
    `_process_one_problem` — фиксированные плейсхолдеры вроде
    `['спрос','предложение','равновесие']` больше не гарантированно
    проходят её для произвольного текста задачи)."""
    m = _SHORTLIST_RE.search(user_text or '')
    if not m:
        return []
    return [t for t in m.group(1).split('; ') if t]


def _valid_call1_json(user_text, theme_idx=0):
    theme_id = taxonomy.theme_ids()[theme_idx]
    tag_id = taxonomy.tag_ids()[theme_idx]
    shortlist = _shortlist_from_user_text(user_text)
    concepts = shortlist[:3]
    return json.dumps({
        'topic_primary': theme_id, 'topics_secondary': [], 'tags': [tag_id],
        'given': 'Линейная функция спроса', 'find': 'Точку равновесия',
        'econ_concepts': concepts,
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


def _real_png(size=(20, 20)):
    """Настоящий декодируемый PNG — `prepare_raster_image` открывает байты
    через Pillow, суррогатный заголовок картинку не проходит."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, color=(200, 50, 50)).save(buf, format='PNG')
    return buf.getvalue()


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
        self.manifest_path = self.tmp_dir / 'run300_sample_ids.json'

    def _patch_paths(self):
        return mock.patch.multiple(
            run_cmd,
            RAW_LOG_PATH=self.raw_path,
            PARSED_LOG_PATH=self.parsed_path,
            METRICS_PATH=self.metrics_path,
            SAMPLE_MANIFEST_PATH=self.manifest_path,
        )

    def test_полный_прогон_без_брака_создаёт_три_файла(self):
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

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
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='same-run-id')

        calls = []

        def counting_complete(model, blocks, user_text, schema, effort, images=None):
            calls.append(model)
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

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
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

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

    def test_images_sent_считается_по_реальным_figures_а_не_нулём(self):
        # Баг живого чек-поинта 02.09.2026 (третья пересъёмка): журнал
        # (`run_raw.jsonl`) не хранит `images_sent`/`tikz`, и
        # `_rows_from_log` раньше молча ставил 0 при ЛЮБОМ резюмировании —
        # `run_metrics.json` врал нулём, даже когда картинки реально ушли
        # в вызов 1 (проверено на боевом прогоне: 19 задач/29 картинок по
        # факту при заявленных 0).
        figured_problem = self.problems[0]
        ProblemFigure.objects.create(
            problem=figured_problem, tikz_hash='raster1', source_field='statement',
            content_type='image/png', image_data=_real_png())

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='images-run')

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['images_sent_total'], 1)

        parsed = [json.loads(line) for line in
                 self.parsed_path.read_text(encoding='utf-8').strip().splitlines()]
        figured_row = next(p for p in parsed if p['problem_id'] == figured_problem.id)
        self.assertEqual(figured_row['images_sent'], 1)

    def test_запрос_с_цифрой_выбрасывается_и_не_вызывает_повтора(self):
        """Фаза 1.2 сквозняком: восемь запросов, два с цифрами — вызов 2
        проходит с первого раза (повтора нет, денег за него не платим),
        в журнале остаётся шесть запросов и текст обоих выброшенных."""
        call2 = json.loads(VALID_CALL2_JSON)
        call2['search_queries'] = [
            'спрос и предложение', 'эластичность спроса',
            'налог на производителя', 'потолок цены',
            'излишек потребителя', 'равновесие рынка',
            'цена 100 рублей', 'выпуск при Q = 20']

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1
                              else json.dumps(call2, ensure_ascii=False))

        with self._patch_paths(),                 mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='test-drop-1')

        parsed = [json.loads(line) for line in
                 self.parsed_path.read_text(encoding='utf-8').strip().splitlines()]
        self.assertTrue(parsed)
        for row in parsed:
            self.assertFalse(row['defect'], row['call2_violations'])
            self.assertFalse(row['call2_retried'])
            self.assertEqual(len(row['search_queries']), 6)
            self.assertEqual(sorted(row['dropped_queries']),
                             ['выпуск при Q = 20', 'цена 100 рублей'])

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['dropped_queries_total'], 2 * len(self.problems))
        self.assertEqual(metrics['rows_with_dropped_queries'], len(self.problems))
        self.assertEqual(metrics['rows_under_5_queries'], 0)
        self.assertEqual(metrics['sweep_detector']['changed'], 0)

    def test_после_выброса_меньше_пяти_запросов_мягкое_без_повтора(self):
        """Шесть запросов, четыре с цифрами — остаётся два: мягкое
        нарушение, повтора нет, браком не считается."""
        call2 = json.loads(VALID_CALL2_JSON)
        call2['search_queries'] = [
            'спрос и предложение', 'эластичность спроса',
            'цена 100 рублей', 'выпуск 20 единиц',
            'налог 5 процентов', 'доход 1000 рублей']

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1
                              else json.dumps(call2, ensure_ascii=False))

        with self._patch_paths(),                 mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='test-drop-2')

        parsed = [json.loads(line) for line in
                 self.parsed_path.read_text(encoding='utf-8').strip().splitlines()]
        for row in parsed:
            self.assertFalse(row['defect'], row['call2_violations'])
            self.assertFalse(row['call2_retried'])
            self.assertEqual(len(row['search_queries']), 2)
            self.assertTrue(any('search_queries' in v
                                for v in row['soft_violations']),
                            row['soft_violations'])

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['rows_under_5_queries'], len(self.problems))
        self.assertEqual(metrics['defects'], 0)

    def test_журнал_хранит_сырой_ответ_а_не_постобработанный(self):
        """`run_raw.jsonl` — СЫРОЙ ответ модели: выброшенные запросы обязаны
        остаться в нём, иначе восстановление метрик из журнала не увидит
        ни одного выброса и соврёт нулём (тот же класс бага, что уже был с
        `images_sent`)."""
        call2 = json.loads(VALID_CALL2_JSON)
        call2['search_queries'] = ['спрос', 'предложение', 'равновесие',
                                   'налог', 'субсидия', 'цена 100 рублей']

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1
                              else json.dumps(call2, ensure_ascii=False))

        with self._patch_paths(),                 mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='test-drop-3')

        raw = [json.loads(line) for line in
              self.raw_path.read_text(encoding='utf-8').strip().splitlines()]
        call2_entries = [e for e in raw if e['call'] == 'call2']
        self.assertTrue(call2_entries)
        for entry in call2_entries:
            self.assertIn('цена 100 рублей',
                          entry['raw_response']['search_queries'])

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['dropped_queries_total'], len(self.problems))

    def test_фикстуры_рендерера_исключены_из_выборки(self):
        fixture_source = Source.objects.create(name=run_cmd.SERVICE_FIXTURE_SOURCE)
        fixture_problem = Problem.objects.create(statement='Служебная фикстура.')
        SourceReference.objects.create(problem=fixture_problem, source=fixture_source)

        ids = list(run_cmd.battle_queryset().values_list('id', flat=True))
        self.assertNotIn(fixture_problem.id, ids)
        self.assertTrue(all(p.id in ids for p in self.problems))


class RunQualityTrackerTests(TestCase):
    """Фаза 1.1 (решение владельца 02.09.2026, четвёртая пересъёмка):
    автостоп считает ФИНАЛЬНЫЙ БРАК, а не долю задач, потребовавших
    повтора. Доля повторов — это про деньги, они огорожены `--max-cost`."""

    def _row(self, defect=False, retried=False, soft=False):
        return {
            'call1_ok': not defect, 'call2_ok': True,
            'call1_retried': retried, 'call2_retried': False,
            'call1_soft_violations': ['мягкое'] if soft else [],
            'call2_soft_violations': [],
        }

    def _feed(self, tracker, total, defects, retries, softs=0):
        for i in range(total):
            tracker.record(self._row(defect=i < defects, retried=i < retries,
                                     soft=i < softs))

    def test_много_повторов_мало_брака_не_останавливает(self):
        """Зубастость задания: 20% повторов и 2% брака — не останавливается."""
        tracker = run_cmd.RunQualityTracker()
        self._feed(tracker, total=200, defects=4, retries=40)
        self.assertFalse(tracker.breached)
        defect_pct, retry_pct, _ = tracker.pcts()
        self.assertAlmostEqual(defect_pct, 2.0)
        self.assertAlmostEqual(retry_pct, 20.0)

    def test_мало_повторов_много_брака_останавливает(self):
        """Зубастость задания: 4% повторов и 8% брака — останавливается."""
        tracker = run_cmd.RunQualityTracker()
        self._feed(tracker, total=200, defects=16, retries=8)
        self.assertTrue(tracker.breached)
        defect_pct, retry_pct, _ = tracker.pcts()
        self.assertAlmostEqual(defect_pct, 8.0)
        self.assertAlmostEqual(retry_pct, 4.0)

    def test_порог_ровно_пять_процентов_не_превышен(self):
        """Порог — «больше 5%», а не «5% и больше»."""
        tracker = run_cmd.RunQualityTracker()
        self._feed(tracker, total=200, defects=10, retries=0)
        self.assertFalse(tracker.breached)

    def test_малая_выборка_не_судится(self):
        """Двадцать задач — не приговор: при пороге 5% две неудачи подряд
        читаются как 10% и остановили бы прогон на шуме."""
        tracker = run_cmd.RunQualityTracker()
        self._feed(tracker, total=20, defects=20, retries=20)
        self.assertFalse(tracker.breached)

    def test_мягкие_нарушения_считаются_но_не_останавливают(self):
        tracker = run_cmd.RunQualityTracker()
        self._feed(tracker, total=200, defects=0, retries=0, softs=180)
        self.assertFalse(tracker.breached)
        _, _, soft_pct = tracker.pcts()
        self.assertAlmostEqual(soft_pct, 90.0)

    def test_порог_по_умолчанию_пять(self):
        self.assertEqual(run_cmd.FINAL_DEFECT_STOP_PCT, 5.0)
        self.assertEqual(run_cmd.RunQualityTracker().stop_pct, 5.0)


class SweepDetectorTests(TestCase):
    """§12 правило 2: расхождение в защищённых полях — это нарушение P0,
    а не «немного разошлось». Прогон в базу не пишет вовсе."""

    def setUp(self):
        self.problem = Problem.objects.create(
            statement='Условие про рынок.', answer='42', solution='Решение.')

    def test_без_правок_ноль_расхождений(self):
        before = run_cmd.protected_fields_digest([self.problem.id])
        after = run_cmd.protected_fields_digest([self.problem.id])
        report = run_cmd.sweep_report(before, after)
        self.assertEqual(report['changed'], 0)
        self.assertEqual(report['checked'], 1)

    def test_правка_условия_видна(self):
        before = run_cmd.protected_fields_digest([self.problem.id])
        Problem.objects.filter(id=self.problem.id).update(
            statement='Условие про рынок, но другое.')
        report = run_cmd.sweep_report(
            before, run_cmd.protected_fields_digest([self.problem.id]))
        self.assertEqual(report['changed'], 1)
        self.assertEqual(report['changed_ids'], [self.problem.id])

    def test_правка_подпункта_видна(self):
        from problems.models import ProblemPart
        part = ProblemPart.objects.create(
            problem=self.problem, label='а', statement='Первый подпункт.')
        before = run_cmd.protected_fields_digest([self.problem.id])
        ProblemPart.objects.filter(id=part.id).update(statement='Другой текст.')
        report = run_cmd.sweep_report(
            before, run_cmd.protected_fields_digest([self.problem.id]))
        self.assertEqual(report['changed'], 1)


class StratifiedCheckpointSampleTests(TestCase):
    """Фаза C задания сессии 02.09: контрольная точка — не первые N по id
    (id 1-300 оказались целиком легаси без единой картинки, см. решение
    владельца), а стратифицированная случайная выборка с гарантиями на
    визуальный пласт и пропорцией по источникам."""

    REAL_TIKZ = r'\draw[->] (0,0) -- (1,1);'

    def _make_source(self, name):
        return Source.objects.create(name=name)

    def _make_problem_with_source(self, source, statement='Задача.'):
        p = Problem.objects.create(statement=statement)
        SourceReference.objects.create(problem=p, source=source)
        return p

    def setUp(self):
        self.src_a = self._make_source('Источник A')
        self.src_b = self._make_source('Источник B')

        # 5 настоящих TikZ (все должны попасть в выборку — их меньше
        # MIN_TIKZ).
        self.tikz_problems = []
        for i in range(5):
            p = self._make_problem_with_source(self.src_a, 'Задача с чертежом %d.' % i)
            ProblemFigure.objects.create(
                problem=p, tikz_hash='tikz%d' % i, source_field='statement',
                tikz_source=self.REAL_TIKZ)
            self.tikz_problems.append(p)

        # 60 задач с растровой картинкой в условии — больше MIN_RASTER_IMAGES.
        self.raster_condition_problems = []
        for i in range(60):
            p = self._make_problem_with_source(self.src_a, 'Задача с картинкой %d.' % i)
            ProblemFigure.objects.create(
                problem=p, tikz_hash='raster%d' % i, source_field='statement',
                content_type='image/png', image_data=b'\x89PNG\r\n\x1a\n' + b'0' * 20)
            self.raster_condition_problems.append(p)

        # 25 задач с картинкой у решения — больше MIN_SOLUTION_IMAGES.
        self.raster_solution_problems = []
        for i in range(25):
            p = self._make_problem_with_source(self.src_b, 'Задача, решение %d.' % i)
            ProblemFigure.objects.create(
                problem=p, tikz_hash='sol%d' % i, source_field='solution',
                content_type='image/png', image_data=b'\x89PNG\r\n\x1a\n' + b'0' * 20)
            self.raster_solution_problems.append(p)

        # 300 обычных задач без визуального пласта — фон для пропорции.
        self.plain_problems = [
            self._make_problem_with_source(self.src_a if i % 2 else self.src_b,
                                           'Обычная задача %d.' % i)
            for i in range(300)
        ]

        # служебная фикстура — не должна попасть в выборку никогда.
        fixture_source = Source.objects.create(name=run_cmd.SERVICE_FIXTURE_SOURCE)
        self.fixture_problem = Problem.objects.create(statement='Фикстура.')
        SourceReference.objects.create(problem=self.fixture_problem, source=fixture_source)

    def test_все_настоящие_tikz_попадают_в_выборку(self):
        ids, report = run_cmd.stratified_checkpoint_sample(limit=120, seed=1)
        tikz_ids = {p.id for p in self.tikz_problems}
        self.assertTrue(tikz_ids.issubset(set(ids)))

    def test_минимум_растровых_картинок_условия(self):
        ids, report = run_cmd.stratified_checkpoint_sample(limit=120, seed=1)
        raster_ids = {p.id for p in self.raster_condition_problems}
        self.assertGreaterEqual(len(raster_ids & set(ids)), run_cmd.MIN_RASTER_IMAGES)

    def test_минимум_картинок_у_решения(self):
        ids, report = run_cmd.stratified_checkpoint_sample(limit=120, seed=1)
        solution_ids = {p.id for p in self.raster_solution_problems}
        self.assertGreaterEqual(len(solution_ids & set(ids)), run_cmd.MIN_SOLUTION_IMAGES)

    def test_размер_выборки_не_больше_лимита_и_без_дублей(self):
        ids, report = run_cmd.stratified_checkpoint_sample(limit=120, seed=1)
        self.assertLessEqual(len(ids), 120)
        self.assertEqual(len(ids), len(set(ids)))

    def test_фикстура_рендерера_никогда_не_попадает(self):
        ids, report = run_cmd.stratified_checkpoint_sample(limit=120, seed=1)
        self.assertNotIn(self.fixture_problem.id, ids)

    def test_детерминирована_одним_зерном(self):
        ids1, _ = run_cmd.stratified_checkpoint_sample(limit=120, seed=42)
        ids2, _ = run_cmd.stratified_checkpoint_sample(limit=120, seed=42)
        self.assertEqual(ids1, ids2)

    def test_разное_зерно_разная_выборка(self):
        ids1, _ = run_cmd.stratified_checkpoint_sample(limit=120, seed=1)
        ids2, _ = run_cmd.stratified_checkpoint_sample(limit=120, seed=2)
        self.assertNotEqual(ids1, ids2)

    def test_отчёт_упоминает_источники_и_визуальные_числа(self):
        ids, report = run_cmd.stratified_checkpoint_sample(limit=120, seed=1)
        text = '\n'.join(report)
        self.assertIn('Источник A', text)
        self.assertIn('Источник B', text)
        self.assertIn('TikZ', text)


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
        self.manifest_path = self.tmp_dir / 'run300_sample_ids.json'

    def test_метрики_считаются_без_внешнего_ai_prices(self):
        from django.conf import settings
        self.assertNotIn(run_cmd.GLM_MODEL, getattr(settings, 'AI_PRICES', {}))

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

        with mock.patch.multiple(
                run_cmd, RAW_LOG_PATH=self.raw_path, PARSED_LOG_PATH=self.parsed_path,
                METRICS_PATH=self.metrics_path, SAMPLE_MANIFEST_PATH=self.manifest_path), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=2, run_id='prices-regression')

        self.assertTrue(self.metrics_path.exists())
        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['total_processed'], len(self.problems))
        self.assertGreater(Decimal(metrics['usage_totals']['cost_usd']), 0)
