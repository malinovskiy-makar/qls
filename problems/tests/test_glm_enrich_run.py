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
    'problem_type': 'тест: короткий ответ', 'difficulty': 2,
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
class GlmVariantReasoningEffortTests(TestCase):
    """Фаза 2 (2026-09-04): уровень рассуждения — 'high', а не 'low', для
    ОБОИХ вызовов. 'medium' не выбран сознательно: реальный API Z.AI для
    GLM-5.3-Flash принимает только reasoning_effort ∈ {low, high, max} —
    решение владельца при разборе этого ограничения (задание сессии,
    Фаза 2)."""

    def test_оба_вызова_на_high(self):
        self.assertEqual(run_cmd.GLM_VARIANT['call1_effort'], 'high')
        self.assertEqual(run_cmd.GLM_VARIANT['call2_effort'], 'high')


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
        self.battle_manifest_path = self.tmp_dir / 'run_full_sample_ids.json'

    def _patch_paths(self):
        return mock.patch.multiple(
            run_cmd,
            RAW_LOG_PATH=self.raw_path,
            PARSED_LOG_PATH=self.parsed_path,
            METRICS_PATH=self.metrics_path,
            SAMPLE_MANIFEST_PATH=self.manifest_path,
            BATTLE_MANIFEST_PATH=self.battle_manifest_path,
        )

    def test_боевой_лимит_берёт_весь_корпус_а_не_манифест_чек_поинта(self):
        """⚠️ Самая дорогая ошибка этого пути: манифест контрольной точки
        содержит ровно её 300 задач, и `--limit 50000` при живом манифесте
        молча прогнал бы их по второму разу вместо корпуса. Боевой лимит
        (больше `CHECKPOINT_LIMIT`) обязан взять `battle_queryset()` и
        писать СВОЙ манифест, не трогая чек-поинт."""
        with open(self.manifest_path, 'w', encoding='utf-8') as fh:
            json.dump({'seed': 1, 'limit': 300,
                      'ids': [self.problems[0].id]}, fh)
        before = self.manifest_path.read_text(encoding='utf-8')

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=50000, max_cost=100.0,
                        workers=3, chunk=2, run_id='test-battle-1')

        battle = json.loads(self.battle_manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(sorted(battle['ids']),
                         sorted(p.id for p in self.problems))
        # манифест чек-поинта не тронут
        self.assertEqual(self.manifest_path.read_text(encoding='utf-8'), before)
        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['total_processed'], len(self.problems))

    def test_battle_manifest_редиректит_и_не_трогает_манифест_первого_прогона(self):
        """⚠️ Найдено владельцем перед запуском: `_battle_sample` берёт
        существующий манифест КАК ЕСТЬ, даже если с тех пор изменился
        `battle_queryset()` (например добавился фильтр content_status).
        У второго прогона манифест первого (`run_full_sample_ids.json`)
        уже существует и содержит needs_fix/junk-задачи, отфильтрованные
        ТОЛЬКО в свежем battle_queryset() — без своего пути второй прогон
        унаследовал бы устаревший список молча."""
        needs_fix = Problem.objects.create(
            statement='Битая задача.', content_status='needs_fix')
        stale_ids = [p.id for p in self.problems] + [needs_fix.id]
        with open(self.battle_manifest_path, 'w', encoding='utf-8') as fh:
            json.dump({'seed': 1, 'limit': 50000, 'ids': stale_ids}, fh)
        before = self.battle_manifest_path.read_text(encoding='utf-8')

        custom_battle_manifest = self.tmp_dir / 'run2_full_sample_ids.json'

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=50000, max_cost=100.0,
                        workers=3, chunk=2, run_id='test-battle-manifest-1',
                        battle_manifest=str(custom_battle_manifest))

        # старый манифест первого прогона не тронут
        self.assertEqual(self.battle_manifest_path.read_text(encoding='utf-8'), before)

        new_battle = json.loads(custom_battle_manifest.read_text(encoding='utf-8'))
        self.assertEqual(sorted(new_battle['ids']),
                         sorted(p.id for p in self.problems))
        self.assertNotIn(needs_fix.id, new_battle['ids'])

    def test_куски_не_теряют_и_не_дублируют_задачи(self):
        """Прогон кусками по 2 задачи обязан дать ровно тот же журнал, что
        и одним куском: ни потерь, ни дублей строк в run_parsed.jsonl."""
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=2, chunk=2,
                        run_id='test-chunk-1')

        parsed = [json.loads(line) for line in
                 self.parsed_path.read_text(encoding='utf-8').strip().splitlines()]
        ids = [row['problem_id'] for row in parsed]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids), sorted(p.id for p in self.problems))

    def test_контрольная_строка_показывает_расход_всего_прогона(self):
        """⚠️ Расход в контрольной строке НЕ МОЖЕТ УМЕНЬШАТЬСЯ. Баг боевого
        прогона 02.09.2026: `on_progress` получает расход текущего КУСКА
        (его счётчик начинается с нуля на каждый кусок), и строка показала
        $1,0814 на 2000 задачах, затем $1,0411 на 4000 — как будто деньги
        вернулись. На многочасовом прогоне без человека рядом такое число
        вводит в заблуждение ровно там, где смотрят на бюджет."""
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

        out = io.StringIO()
        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete), \
                mock.patch.object(run_cmd, 'CHECKPOINT_EVERY', 2):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=1, chunk=2,
                        run_id='test-progress-1', stdout=out)

        spends = [float(m) for m in
                 re.findall(r'потрачено \$([0-9.]+)', out.getvalue())]
        self.assertGreaterEqual(len(spends), 3, out.getvalue())
        self.assertEqual(spends, sorted(spends),
                         'расход в контрольной строке уменьшился: %s' % spends)
        self.assertGreater(spends[-1], spends[0])

    def test_потолок_расхода_общий_на_все_куски(self):
        """`--max-cost` считается по ВСЕМУ прогону, а не заново на каждый
        кусок: иначе потолок $70 при двадцати кусках означал бы $1400."""
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON,
                             input_tokens=2_000_000, cache_read_tokens=0)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=0.20, workers=1, chunk=1,
                        run_id='test-budget-1')

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        # 2 млн входных токенов по $0.075/млн = $0.15 за вызов; потолок
        # $0.20 обязан остановить прогон задолго до шести задач.
        self.assertLess(metrics['total_processed'], len(self.problems))
        self.assertLessEqual(Decimal(metrics['usage_totals']['cost_usd']),
                             Decimal('0.45'))

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

    def test_подстраховка_старым_журналом_сквозняком(self):
        """Фаза 4.2 (2026-09-04) целиком через реальную команду: все
        задачи бракуются (INVALID_CALL1_JSON не проходит проверку даже
        после повтора), но старый журнал знает про часть из них — те
        выходят из прогона рескьюнутыми, а не пустыми."""
        rescuable = self.problems[:2]
        old_parsed_path = self.tmp_dir / 'run_parsed.jsonl'
        with open(old_parsed_path, 'w', encoding='utf-8') as fh:
            for p in rescuable:
                fh.write(json.dumps(_old_run1_row(p.id), ensure_ascii=False))
                fh.write('\n')

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(INVALID_CALL1_JSON if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=3, run_id='test-fallback-1',
                        fallback_parsed=str(old_parsed_path))

        parsed = [json.loads(line) for line in
                 self.parsed_path.read_text(encoding='utf-8').strip().splitlines()]
        by_id = {p['problem_id']: p for p in parsed}

        for p in rescuable:
            row = by_id[p.id]
            self.assertIn('call1', row['fallback_from_run1'])
            self.assertEqual(row['topic_primary'], '1')
            self.assertEqual(row['given'], 'Старое дано')
            self.assertEqual(row['missing_required_fields'], [])

        not_rescuable = [p for p in self.problems if p not in rescuable]
        for p in not_rescuable:
            row = by_id[p.id]
            self.assertEqual(row['fallback_from_run1'], [])
            self.assertTrue(row['missing_required_fields'])

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['fallback_from_run1']['rows_call1'], 2)
        self.assertEqual(metrics['rows_with_missing_fields'],
                         len(not_rescuable))

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

    def test_решение_уходит_в_вызов_1_и_считается_в_журнале(self):
        """Фаза 1 (2026-09-04, реверс §3.4 API_RUN_MASTER): задача с
        решением получает блок решения в вызове 1, задача без решения —
        нет. Журнал и метрики обязаны знать, у скольких это сработало."""
        with_solution = self.problems[0]
        with_solution.solution = 'Из условия равновесия находим оптимум монополиста.'
        with_solution.save()
        without_solution = self.problems[1]

        call1_user_texts = []

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            if is_call1:
                call1_user_texts.append(user_text)
                return _FakeReply(_valid_call1_json(user_text))
            return _FakeReply(VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=1, run_id='test-solution-1')

        self.assertTrue(any('оптимум монополиста' in t for t in call1_user_texts))

        parsed = [json.loads(line) for line in
                 self.parsed_path.read_text(encoding='utf-8').strip().splitlines()]
        row_with = next(p for p in parsed if p['problem_id'] == with_solution.id)
        row_without = next(p for p in parsed if p['problem_id'] == without_solution.id)
        self.assertTrue(row_with['solution_sent'])
        self.assertGreater(row_with['solution_tokens'], 0)
        self.assertFalse(row_without['solution_sent'])
        self.assertEqual(row_without['solution_tokens'], 0)

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        self.assertEqual(metrics['solution_sent_total'], 1)

    def test_raw_out_редиректит_журнал_и_не_трогает_путь_по_умолчанию(self):
        """Фаза 4.3 (2026-09-04): у второго прогона нет права писать в
        `run_raw.jsonl` первого — тот журнал неприкосновенен ($21,57
        оплаченной работы). `--parsed-out`/`--metrics-out` такой флаг уже
        имели, а сырой журнал молча писался по ХАРДКОДНОМУ пути — эта
        дыра и чинится."""
        custom_raw = self.tmp_dir / 'run2_raw.jsonl'

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1 else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn', return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=2, run_id='test-rawout-1',
                        raw_out=str(custom_raw))

        self.assertTrue(custom_raw.exists())
        self.assertFalse(self.raw_path.exists())

        raw_lines = custom_raw.read_text(encoding='utf-8').strip().splitlines()
        self.assertEqual(len(raw_lines), len(self.problems) * 2)

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

    def test_content_status_не_ok_исключён_из_выборки(self):
        """Фаза 4.1 (2026-09-04): битый текст в прогон не идёт — обогащение
        битого текста даёт битые поля. `battle_queryset()` раньше по
        `content_status` не фильтровала вовсе (найдено прошлой сессией,
        не починено — чиним здесь)."""
        needs_fix = Problem.objects.create(
            statement='Требует доработки.', content_status='needs_fix')
        junk = Problem.objects.create(statement='Мусор.', content_status='junk')

        ids = list(run_cmd.battle_queryset().values_list('id', flat=True))

        self.assertNotIn(needs_fix.id, ids)
        self.assertNotIn(junk.id, ids)
        self.assertTrue(all(p.id in ids for p in self.problems))


def _old_run1_row(problem_id, **overrides):
    """Строка старого журнала (`run_parsed.jsonl` первого прогона) —
    то, во что рассчитывает попасть подстраховка Фазы 4.2."""
    base = {
        'problem_id': problem_id,
        'topic_primary': '1', 'topics_secondary': [], 'tags': ['1.1'],
        'given': 'Старое дано', 'find': 'Старое найти',
        'econ_concepts': ['спрос', 'предложение', 'равновесие'],
        'concepts_offlist': [], 'task_nature': 'расчётная', 'features_1': [],
        'topic_confidence': 'высокая',
        'search_queries': ['старый запрос ' + w for w in
                          ('один', 'два', 'три', 'четыре', 'пять')],
        'plot': 'Старый сюжет.', 'hints': ['раз', 'два', 'три'],
        'text_quality': 'чистая', 'text_quality_note': '',
        'problem_type': 'тест: короткий ответ', 'difficulty': 3,
        'difficulty_note': 'старое', 'answer_consistency': 'согласован',
        'title_candidate': 'Старый заголовок',
    }
    base.update(overrides)
    return base


class ParsedRowFallbackTests(TestCase):
    """Фаза 4.2 (2026-09-04): второй прогон не может сделать банк хуже —
    задача, не прошедшая проверки даже после повтора, берёт поля
    провалившегося вызова из журнала ПЕРВОГО прогона, а не остаётся с
    пустыми/битыми полями."""

    def setUp(self):
        self.problem = Problem.objects.create(
            statement='Задача про рынок.', solution='Из равновесия P=MC.')

    def _row(self, call1_ok=True, call2_ok=True, call1=None, call2=None):
        return {
            'problem_id': self.problem.id,
            'call1': call1 or {'topic_primary': '2', 'topics_secondary': [],
                               'tags': ['2.1'], 'given': 'Новое дано',
                               'find': 'Новое найти', 'econ_concepts': [],
                               'concepts_offlist': [], 'task_nature': 'расчётная',
                               'features_1': [], 'topic_confidence': 'высокая'},
            'call1_ok': call1_ok, 'call1_retried': False,
            'call1_violations': [], 'call1_soft_violations': [],
            'call2': call2 or {'search_queries': ['a', 'b'], 'plot': None,
                               'hints': None, 'text_quality': 'чистая',
                               'text_quality_note': '', 'problem_type': 'тест: короткий ответ',
                               'difficulty': 2, 'difficulty_note': '',
                               'answer_consistency': 'согласован',
                               'title_candidate': 'Новый заголовок'},
            'call2_ok': call2_ok, 'call2_retried': False,
            'call2_violations': [], 'call2_soft_violations': [],
            'images_sent': 0, 'tikz': {'replaced': 0, 'truncated': 0},
            'solution_sent': True, 'solution_tokens': 42,
            'solution_truncated': False,
        }

    def test_call1_брак_без_подстраховки_остаётся_как_было(self):
        row = self._row(call1_ok=False)
        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=None)
        self.assertEqual(parsed['topic_primary'], '2')  # своё, не подменено
        self.assertEqual(parsed['fallback_from_run1'], [])

    def test_call1_брак_с_подстраховкой_берёт_поля_из_старого_журнала(self):
        row = self._row(call1_ok=False)
        fallback = {self.problem.id: _old_run1_row(self.problem.id)}

        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=fallback)

        self.assertEqual(parsed['topic_primary'], '1')
        self.assertEqual(parsed['tags'], ['1.1'])
        self.assertEqual(parsed['given'], 'Старое дано')
        self.assertEqual(parsed['find'], 'Старое найти')
        self.assertIn('call1', parsed['fallback_from_run1'])
        # вызов 2 был ok — его подстраховка не касается
        self.assertEqual(parsed['title_candidate'], 'Новый заголовок')
        self.assertNotIn('call2', parsed['fallback_from_run1'])

    def test_call2_брак_с_подстраховкой_берёт_поля_из_старого_журнала(self):
        row = self._row(call2_ok=False)
        fallback = {self.problem.id: _old_run1_row(self.problem.id)}

        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=fallback)

        self.assertEqual(parsed['title_candidate'], 'Старый заголовок')
        self.assertEqual(parsed['difficulty'], 3)
        self.assertEqual(parsed['hints'], ['раз', 'два', 'три'])
        self.assertIn('call2', parsed['fallback_from_run1'])
        self.assertEqual(parsed['topic_primary'], '2')  # вызов 1 был ok
        self.assertNotIn('call1', parsed['fallback_from_run1'])

    def test_оба_брака_подставляют_оба_набора_полей(self):
        row = self._row(call1_ok=False, call2_ok=False)
        fallback = {self.problem.id: _old_run1_row(self.problem.id)}

        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=fallback)

        self.assertEqual(parsed['fallback_from_run1'], ['call1', 'call2'])
        self.assertEqual(parsed['topic_primary'], '1')
        self.assertEqual(parsed['title_candidate'], 'Старый заголовок')
        self.assertEqual(parsed['missing_required_fields'], [])

    def test_ok_строка_подстраховку_игнорирует(self):
        row = self._row(call1_ok=True, call2_ok=True)
        fallback = {self.problem.id: _old_run1_row(self.problem.id)}

        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=fallback)

        self.assertEqual(parsed['fallback_from_run1'], [])
        self.assertEqual(parsed['topic_primary'], '2')

    def test_брак_без_подстраховки_в_журнале_виден_в_missing_required_fields(self):
        """Задачи, которых НЕТ в старом журнале (например, добавленной уже
        после первого прогона), рескью не получают — список пропавших
        полей делает эту брешь видимой владельцу поимённо, а не молча."""
        row = self._row(call1_ok=False, call2=None)
        row['call1'] = {}  # ничего не разобралось
        parsed = run_cmd.parsed_row(row, self.problem, fallback_index={})
        self.assertIn('topic_primary', parsed['missing_required_fields'])
        self.assertEqual(parsed['fallback_from_run1'], [])

    def test_не_задача_не_считается_недостающими_given_find(self):
        row = self._row(call1_ok=True, call2_ok=True,
                        call1={'topic_primary': '29', 'topics_secondary': [],
                              'tags': ['29.5'], 'given': '', 'find': '',
                              'econ_concepts': [], 'concepts_offlist': [],
                              'task_nature': 'не_задача', 'features_1': [],
                              'topic_confidence': 'низкая'},
                        call2={'search_queries': ['a', 'b'], 'plot': None,
                              'hints': None, 'text_quality': 'не_задача',
                              'text_quality_note': '', 'problem_type': 'не_задача',
                              'difficulty': None, 'difficulty_note': '',
                              'answer_consistency': 'решение_отсутствует_проверить_нечем',
                              'title_candidate': 'Обрывок'})
        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=None)
        self.assertEqual(parsed['missing_required_fields'], [])

    def test_решение_есть_но_plot_hints_пусты_считается_недостающим(self):
        row = self._row(call1_ok=True, call2_ok=True,
                        call2={'search_queries': ['a', 'b'], 'plot': None,
                              'hints': None, 'text_quality': 'чистая',
                              'text_quality_note': '', 'problem_type': 'тест: короткий ответ',
                              'difficulty': 2, 'difficulty_note': '',
                              'answer_consistency': 'согласован',
                              'title_candidate': 'Заголовок'})
        # solution_sent=True в _row по умолчанию — решение реально подавалось
        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=None)
        self.assertIn('plot', parsed['missing_required_fields'])
        self.assertIn('hints', parsed['missing_required_fields'])


class NormalizeLegacyProblemTypeTests(TestCase):
    """Фаза 4 (04.09.2026, разбор run2-corpus-20260904): 11 строк с
    отменённым коммитом 2104203 значением `problem_type = 'открытый_
    ответ'` — пришли через подстраховку старым журналом (Фаза 4.2), не из
    свежего ответа GLM. `single_freetext` — категория ТЕСТА на SolveHub, а
    не признак «ответ короткий»."""

    def test_обычное_значение_не_трогается(self):
        value, was_legacy = run_cmd.normalize_legacy_problem_type(
            'тест: короткий ответ', check_type=None)
        self.assertEqual(value, 'тест: короткий ответ')
        self.assertFalse(was_legacy)

    def test_single_freetext_даёт_короткий_ответ(self):
        value, was_legacy = run_cmd.normalize_legacy_problem_type(
            run_cmd.LEGACY_OPEN_ANSWER_VALUE, check_type='single_freetext')
        self.assertEqual(value, 'тест: короткий ответ')
        self.assertTrue(was_legacy)

    def test_check_type_отсутствует_даёт_развёрнутый_ответ(self):
        value, was_legacy = run_cmd.normalize_legacy_problem_type(
            run_cmd.LEGACY_OPEN_ANSWER_VALUE, check_type=None)
        self.assertEqual(value, 'задача с развёрнутым ответом')
        self.assertTrue(was_legacy)

    def test_check_type_неоднозначный_даёт_развёрнутый_ответ(self):
        """`uncheckable`/`multiple_questions` — свойство ДАННЫХ источника
        (ответа нет / несколько вопросов), не тип задачи; соответствия 1:1
        нет, поэтому уходит в тот же безопасный дефолт, что и отсутствие
        check_type (два реальных случая из 11 найденных строк)."""
        for check_type in ('uncheckable', 'multiple_questions'):
            value, was_legacy = run_cmd.normalize_legacy_problem_type(
                run_cmd.LEGACY_OPEN_ANSWER_VALUE, check_type=check_type)
            self.assertEqual(value, 'задача с развёрнутым ответом')
            self.assertTrue(was_legacy)


class ParsedRowLegacyProblemTypeTests(TestCase):
    """Как `ParsedRowFallbackTests`, но конкретно про легаси-значение,
    попавшее в строку через подстраховку (Фаза 4.2) — обычным путём
    (свежий ответ GLM) оно попасть не может: `prompts_v2.PROBLEM_TYPE`
    его не содержит, схема отклоняет как жёсткое нарушение."""

    def setUp(self):
        self.problem = Problem.objects.create(statement='Задача про рынок.')

    def _row_with_bad_call2(self):
        row = ParsedRowFallbackTests._row(self, call2_ok=False)
        return row

    def test_легаси_значение_из_подстраховки_нормализуется_с_check_type(self):
        row = self._row_with_bad_call2()
        fallback = {self.problem.id: _old_run1_row(
            self.problem.id, problem_type=run_cmd.LEGACY_OPEN_ANSWER_VALUE)}

        parsed = run_cmd.parsed_row(
            row, self.problem, fallback_index=fallback,
            check_type_index={self.problem.id: 'single_freetext'})

        self.assertEqual(parsed['problem_type'], 'тест: короткий ответ')
        self.assertIn('problem_type_legacy_value', parsed['soft_violations'])

    def test_легаси_значение_без_check_type_index_даёт_развёрнутый_ответ(self):
        row = self._row_with_bad_call2()
        fallback = {self.problem.id: _old_run1_row(
            self.problem.id, problem_type=run_cmd.LEGACY_OPEN_ANSWER_VALUE)}

        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=fallback,
                                    check_type_index=None)

        self.assertEqual(parsed['problem_type'], 'задача с развёрнутым ответом')
        self.assertIn('problem_type_legacy_value', parsed['soft_violations'])

    def test_обычное_значение_из_подстраховки_не_помечается_легаси(self):
        row = self._row_with_bad_call2()
        fallback = {self.problem.id: _old_run1_row(self.problem.id)}  # 'тест: короткий ответ'

        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=fallback)

        self.assertEqual(parsed['problem_type'], 'тест: короткий ответ')
        self.assertNotIn('problem_type_legacy_value', parsed['soft_violations'])


class PayloadShapeTests(TestCase):
    """Форма ответа модели (2026-09-04, разбор падения боевого прогона
    `run2-corpus-20260904`).

    Прогон отработал 37 035 задач и заплатил $31,46, после чего сборка
    результата легла целиком на `AttributeError: 'list' object has no
    attribute 'get'` — шесть финальных ответов вызова 2 пришли массивом
    из нескольких кусков вместо объекта. Проверяется ровно два свойства:
    объект в массиве из одного элемента разворачивается, а любая другая
    форма даёт БРАК и не роняет сборку."""

    def setUp(self):
        self.problem = Problem.objects.create(
            statement='Задача про рынок.', solution='Из равновесия P=MC.')

    def _call2(self):
        return {'search_queries': ['a', 'b'], 'plot': None, 'hints': None,
                'text_quality': 'чистая', 'text_quality_note': '',
                'problem_type': 'тест: короткий ответ', 'difficulty': 2,
                'difficulty_note': '', 'answer_consistency': 'согласован',
                'title_candidate': 'Новый заголовок'}

    def _row(self, call2, call2_ok=True, problem_id=None):
        return {
            'problem_id': problem_id or self.problem.id,
            'call1': {'topic_primary': '2', 'topics_secondary': [],
                      'tags': ['2.1'], 'given': 'Дано', 'find': 'Найти',
                      'econ_concepts': [], 'concepts_offlist': [],
                      'task_nature': 'расчётная', 'features_1': [],
                      'topic_confidence': 'высокая'},
            'call1_ok': True, 'call1_retried': False,
            'call1_violations': [], 'call1_soft_violations': [],
            'call2': call2,
            'call2_ok': call2_ok, 'call2_retried': False,
            'call2_violations': [], 'call2_soft_violations': [],
            'images_sent': 0, 'tikz': {'replaced': 0, 'truncated': 0},
            'solution_sent': True, 'solution_tokens': 42,
            'solution_truncated': False,
        }

    def test_словарь_собирается_как_обычно(self):
        parsed = run_cmd.parsed_row(self._row(self._call2()), self.problem)

        self.assertEqual(parsed['search_queries'], ['a', 'b'])
        self.assertEqual(parsed['title_candidate'], 'Новый заголовок')
        self.assertTrue(parsed['call2_ok'])
        self.assertFalse(parsed['defect'])
        self.assertNotIn(run_cmd.PAYLOAD_WRAPPED_IN_LIST,
                         parsed['soft_violations'])

    def test_один_словарь_в_массиве_разворачивается(self):
        parsed = run_cmd.parsed_row(self._row([self._call2()]), self.problem)

        self.assertEqual(parsed['search_queries'], ['a', 'b'])
        self.assertEqual(parsed['title_candidate'], 'Новый заголовок')
        self.assertIn(run_cmd.PAYLOAD_WRAPPED_IN_LIST,
                      parsed['soft_violations'])
        # мягкое нарушение банк не портит: вызов остаётся годным
        self.assertTrue(parsed['call2_ok'])
        self.assertFalse(parsed['defect'])

    def test_несколько_элементов_в_массиве_это_брак_без_исключения(self):
        row = self._row([{'search_queries': ['a']}, self._call2()])

        parsed = run_cmd.parsed_row(row, self.problem)

        self.assertFalse(parsed['call2_ok'])
        self.assertTrue(parsed['defect'])
        self.assertIn(run_cmd.PAYLOAD_NOT_OBJECT, parsed['call2_violations'])
        # не угадываем «последний элемент похож на целый»
        self.assertIsNone(parsed['search_queries'])

    def test_строка_вместо_объекта_это_брак_без_исключения(self):
        parsed = run_cmd.parsed_row(self._row('просто текст'), self.problem)

        self.assertFalse(parsed['call2_ok'])
        self.assertTrue(parsed['defect'])
        self.assertIn(run_cmd.PAYLOAD_NOT_OBJECT, parsed['call2_violations'])

    def test_none_вместо_объекта_это_брак_без_исключения(self):
        parsed = run_cmd.parsed_row(self._row(None), self.problem)

        self.assertFalse(parsed['call2_ok'])
        self.assertTrue(parsed['defect'])
        self.assertIn(run_cmd.PAYLOAD_NOT_OBJECT, parsed['call2_violations'])

    def test_кривая_форма_уходит_по_ветке_подстраховки_run1(self):
        row = self._row([{'search_queries': ['a']}, self._call2()])
        fallback = {self.problem.id: _old_run1_row(self.problem.id)}

        parsed = run_cmd.parsed_row(row, self.problem, fallback_index=fallback)

        self.assertEqual(parsed['title_candidate'], 'Старый заголовок')
        self.assertIn('call2', parsed['fallback_from_run1'])

    def test_батч_из_пяти_со_второй_кривой_отдаёт_пять_строк(self):
        problems = [self.problem] + [
            Problem.objects.create(statement='Задача %d.' % i,
                                   solution='Решение %d.' % i)
            for i in range(4)]
        by_id = {p.id: p for p in problems}
        payloads = [self._call2(), [{'a': 1}, {'b': 2}], self._call2(),
                    self._call2(), self._call2()]
        rows = [self._row(payload, problem_id=p.id)
                for p, payload in zip(problems, payloads)]

        parsed = run_cmd.parsed_rows_for(rows, by_id)

        self.assertEqual(len(parsed), 5)
        self.assertEqual(sum(1 for p in parsed if p['defect']), 1)
        self.assertEqual(sum(1 for p in parsed if not p['defect']), 4)

    def test_непредвиденная_ошибка_не_роняет_батч_а_становится_браком(self):
        """Даже если разбор упадёт по причине, которой мы не предусмотрели,
        сборка обязана продолжиться: 37 тысяч оплаченных ответов не могут
        стоить одной кривой строки."""
        rows = [self._row(self._call2()),
                self._row(self._call2(), problem_id=self.problem.id)]
        by_id = {self.problem.id: self.problem}
        real = run_cmd.parsed_row
        calls = {'n': 0}

        def explode(row, problem, fallback_index=None, check_type_index=None):
            calls['n'] += 1
            if calls['n'] == 1:
                raise RuntimeError('внезапно')
            return real(row, problem, fallback_index=fallback_index,
                       check_type_index=check_type_index)

        with mock.patch.object(run_cmd, 'parsed_row', explode):
            parsed = run_cmd.parsed_rows_for(rows, by_id)

        self.assertEqual(len(parsed), 2)
        self.assertTrue(parsed[0]['defect'])
        self.assertIn('внезапно', parsed[0]['parse_crash'])
        self.assertFalse(parsed[1]['defect'])

    def test_метрики_считают_форму_ответа_отдельными_счётчиками(self):
        other = Problem.objects.create(statement='Вторая.', solution='Р.')
        third = Problem.objects.create(statement='Третья.', solution='Р.')
        by_id = {self.problem.id: self.problem, other.id: other,
                 third.id: third}
        rows = [self._row([self._call2()]),
                self._row([{'a': 1}, {'b': 2}], problem_id=other.id),
                self._row(self._call2(), problem_id=third.id)]

        parsed = run_cmd.parsed_rows_for(rows, by_id)
        metrics = run_cmd.build_metrics(parsed, {'cost_usd': '0'})
        anomalies = metrics['payload_anomalies']

        self.assertEqual(anomalies[run_cmd.PAYLOAD_WRAPPED_IN_LIST], 1)
        self.assertEqual(anomalies[run_cmd.PAYLOAD_NOT_OBJECT], 1)
        self.assertEqual(anomalies[run_cmd.PARSE_CRASH], 0)
        self.assertEqual(anomalies['%s_ids' % run_cmd.PAYLOAD_NOT_OBJECT],
                         [other.id])


class RunQualityTrackerTests(TestCase):
    """Фаза 1.1 (решение владельца 02.09.2026, четвёртая пересъёмка):
    автостоп считает ФИНАЛЬНЫЙ БРАК, а не долю задач, потребовавших
    повтора. Доля повторов — это про деньги, они огорожены `--max-cost`."""

    def _row(self, defect=False, retried=False, soft=False,
            find='Точку рыночного равновесия', answer='некоторый ответ',
            solution_sent=False, hints=None):
        return {
            'call1_ok': not defect, 'call2_ok': True,
            'call1_retried': retried, 'call2_retried': False,
            'call1_soft_violations': ['мягкое'] if soft else [],
            'call2_soft_violations': [],
            'call1': {'find': find}, 'call2': {'hints': hints},
            'answer': answer, 'solution_sent': solution_sent,
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


class FindLeaksSolutionTests(TestCase):
    """Фаза 5 (2026-09-04): прямой детектор риска Фазы 1.2 — величина,
    выведенная в решении, не имеет права появиться в `find`."""

    def test_цифра_в_find_ловится_даже_без_ответа(self):
        self.assertTrue(run_cmd.find_leaks_solution('Цена P=10', ''))

    def test_четырёхграмма_с_ответом_ловится(self):
        find = 'Равновесная цена равна половине суммы издержек фирмы'
        answer = 'Равновесная цена равна половине суммы издержек'
        self.assertTrue(run_cmd.find_leaks_solution(find, answer))

    def test_без_цифр_и_без_совпадений_чисто(self):
        find = 'Точку рыночного равновесия'
        answer = 'Цена 10, объём 5'
        self.assertFalse(run_cmd.find_leaks_solution(find, answer))

    def test_короткие_строки_не_роняют_и_не_ложно_срабатывают(self):
        self.assertFalse(run_cmd.find_leaks_solution('Найти цену', 'Ответ'))
        self.assertFalse(run_cmd.find_leaks_solution('', ''))
        self.assertFalse(run_cmd.find_leaks_solution(None, None))


class GuardSentinelTests(TestCase):
    """Фаза 5 (2026-09-04): два новых сторожа поверх финального брака —
    те же правила (скользящий счёт, минимальная выборка 200, порог 5%,
    останавливает любой из трёх)."""

    def _row(self, find_leak=False, solution_sent=False, empty_hints=False):
        row = {
            'call1_ok': True, 'call2_ok': True,
            'call1_retried': False, 'call2_retried': False,
            'call1_soft_violations': [], 'call2_soft_violations': [],
        }
        if find_leak:
            row['call1'] = {'find': 'Цена P=10'}
            row['answer'] = ''
        else:
            row['call1'] = {'find': 'Точку равновесия'}
            row['answer'] = 'некоторый ответ'
        row['solution_sent'] = solution_sent
        row['call2'] = {'hints': None if empty_hints else ['раз', 'два', 'три']}
        return row

    def test_утечка_в_find_выше_порога_останавливает(self):
        tracker = run_cmd.RunQualityTracker()
        for i in range(200):
            tracker.record(self._row(find_leak=i < 20))  # 10%
        self.assertTrue(tracker.breached)
        self.assertIn('find', tracker.breach_reason)

    def test_утечка_в_find_ниже_порога_не_останавливает(self):
        tracker = run_cmd.RunQualityTracker()
        for i in range(200):
            tracker.record(self._row(find_leak=i < 5))  # 2.5%
        self.assertFalse(tracker.breached)

    def test_пустые_подсказки_у_задач_с_решением_выше_порога_останавливает(self):
        tracker = run_cmd.RunQualityTracker()
        # 200 задач С решением — знаменатель именно по ним, а не по total.
        for i in range(200):
            tracker.record(self._row(solution_sent=True, empty_hints=i < 20))  # 10%
        self.assertTrue(tracker.breached)
        self.assertIn('подсказ', tracker.breach_reason)

    def test_пустые_подсказки_ниже_порога_не_останавливает(self):
        tracker = run_cmd.RunQualityTracker()
        for i in range(200):
            tracker.record(self._row(solution_sent=True, empty_hints=i < 5))  # 2.5%
        self.assertFalse(tracker.breached)

    def test_задачи_без_решения_не_считаются_в_знаменатель_подсказок(self):
        """200 задач БЕЗ решения (сторож про подсказки тут неприменим) —
        не должно ложно сработать из-за путаницы знаменателя."""
        tracker = run_cmd.RunQualityTracker()
        for _ in range(200):
            tracker.record(self._row(solution_sent=False, empty_hints=True))
        self.assertFalse(tracker.breached)


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


class Call1OnlyTests(TestCase):
    """Режим `--call1-only` (задание сессии 03.09.2026, фаза 2.7).

    Перегон корпуса переделывает ТОЛЬКО вызов 1: темы, дополнительные темы,
    теги, понятия, «дано», «найти», характер задачи, особенности. Заголовок,
    сложность, тип задачи, подсказки и сюжет живут в вызове 2 — их не
    меняли, и платить за них второй раз незачем (около трети сметы).

    Проверяется главное: ровно один вызов на задачу и НИ ОДНО поле вызова 2
    не потеряно — они переносятся из старого журнала побайтно.
    """

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.problems = [
            Problem.objects.create(statement='Задача %d про рынок и спрос.' % i)
            for i in range(3)
        ]
        self.raw_path = self.tmp_dir / 'run_raw.jsonl'
        self.parsed_path = self.tmp_dir / 'run_parsed.jsonl'
        self.metrics_path = self.tmp_dir / 'run_metrics.json'
        self.manifest_path = self.tmp_dir / 'run300_sample_ids.json'
        self.battle_manifest_path = self.tmp_dir / 'run_full_sample_ids.json'
        self.no_call2_path = self.tmp_dir / 'no_call2.json'

    def _patch_paths(self):
        return mock.patch.multiple(
            run_cmd,
            RAW_LOG_PATH=self.raw_path,
            PARSED_LOG_PATH=self.parsed_path,
            METRICS_PATH=self.metrics_path,
            SAMPLE_MANIFEST_PATH=self.manifest_path,
            BATTLE_MANIFEST_PATH=self.battle_manifest_path,
            NO_CALL2_PATH=self.no_call2_path,
        )

    def _counting_complete_fn(self, calls):
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            calls.append('call1' if is_call1 else 'call2')
            return _FakeReply(_valid_call1_json(user_text) if is_call1
                              else VALID_CALL2_JSON)
        return fake_complete

    def _run(self, calls, call1_only=False, run_id='r1'):
        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn',
                                  return_value=self._counting_complete_fn(calls)):
            call_command('glm_enrich_run', ids=','.join(
                str(p.id) for p in self.problems), max_cost=100.0,
                workers=1, chunk=3, run_id=run_id, call1_only=call1_only)
        return [json.loads(line) for line
                in self.parsed_path.read_text(encoding='utf-8').splitlines()
                if line.strip()]

    def _old_run(self, calls):
        """Полный прогон СТАРОЙ версией промпта — то, что уже оплачено."""
        with mock.patch.object(run_cmd.pilot, 'prompt_fingerprint',
                               return_value='pv-old'):
            return self._run(calls, call1_only=False, run_id='r-old')

    def test_ровно_один_вызов_на_задачу(self):
        self._old_run([])
        calls = []
        with mock.patch.object(run_cmd.pilot, 'prompt_fingerprint',
                               return_value='pv-new'):
            self._run(calls, call1_only=True, run_id='r-new')
        self.assertEqual(
            calls, ['call1'] * len(self.problems),
            'в режиме --call1-only вызов 2 не должен выполняться вовсе')

    def test_поля_вызова_2_совпадают_со_старым_журналом(self):
        old_rows = {r['problem_id']: r for r in self._old_run([])}
        with mock.patch.object(run_cmd.pilot, 'prompt_fingerprint',
                               return_value='pv-new'):
            new_rows = {r['problem_id']: r
                        for r in self._run([], call1_only=True, run_id='r-new')}

        self.assertEqual(set(new_rows), set(old_rows))
        call2_fields = ('search_queries', 'plot', 'hints', 'text_quality',
                        'text_quality_note', 'problem_type', 'difficulty',
                        'difficulty_note', 'answer_consistency',
                        'title_candidate', 'call2_ok', 'call2_retried',
                        'dropped_queries')
        for pid, new in new_rows.items():
            for field in call2_fields:
                self.assertEqual(
                    new.get(field), old_rows[pid].get(field),
                    'поле вызова 2 «%s» задачи #%s разошлось со старым '
                    'журналом' % (field, pid))

    def test_поля_вызова_1_переписаны_а_не_взяты_из_старого(self):
        """Обратная половина: вызов 1 обязан быть НОВЫМ. Иначе перенос
        превратился бы в «ничего не делаем»."""
        self._old_run([])
        theme_ids = taxonomy.theme_ids()

        def other_call1(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            if not is_call1:
                raise AssertionError('вызов 2 не должен выполняться')
            return _FakeReply(_valid_call1_json(user_text, theme_idx=1))

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn',
                                  return_value=other_call1), \
                mock.patch.object(run_cmd.pilot, 'prompt_fingerprint',
                                  return_value='pv-new'):
            call_command('glm_enrich_run', ids=','.join(
                str(p.id) for p in self.problems), max_cost=100.0,
                workers=1, chunk=3, run_id='r-new', call1_only=True)
        rows = [json.loads(line) for line
                in self.parsed_path.read_text(encoding='utf-8').splitlines()
                if line.strip()]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row['topic_primary'], theme_ids[1])

    def test_возобновление_не_платит_за_уже_сделанное(self):
        self._old_run([])
        with mock.patch.object(run_cmd.pilot, 'prompt_fingerprint',
                               return_value='pv-new'):
            self._run([], call1_only=True, run_id='r-new')
            calls2 = []
            self._run(calls2, call1_only=True, run_id='r-new-2')
        self.assertEqual(
            calls2, [],
            'повторный запуск --call1-only обязан пропустить уже сделанный '
            'вызов 1 — иначе резюмирование платило бы заново при каждом '
            'перезапуске')

    def test_задачи_без_старого_вызова_2_попадают_в_список(self):
        """Старого вызова 2 нет вовсе — владелец обязан получить поимённый
        список, а не обнаружить пустой заголовок через месяц."""
        with mock.patch.object(run_cmd.pilot, 'prompt_fingerprint',
                               return_value='pv-new'):
            self._run([], call1_only=True, run_id='r-new')
        payload = json.loads(self.no_call2_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['count'], len(self.problems))
        self.assertEqual(sorted(payload['ids']),
                         sorted(p.id for p in self.problems))

    def test_автостоп_не_считает_браком_отсутствие_вызова_2(self):
        """Мина режима: `call2_ok` у строки отсутствует, и проверка
        `not (call1_ok and call2_ok)` посчитала бы браком КАЖДУЮ задачу —
        автостоп убил бы перегон корпуса на ровном месте."""
        tracker = run_cmd.RunQualityTracker(min_sample=1, call1_only=True)
        tracker.record({'call1_ok': True, 'call1_retried': False})
        defect_pct, _retry, _soft = tracker.pcts()
        self.assertEqual(defect_pct, 0.0)
        self.assertFalse(tracker.breached)
