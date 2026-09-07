# -*- coding: utf-8 -*-
"""`--ids-file` и `--include-nonok` — размыкание замкнутого круга (07.09.2026).

Круг в чистом виде: слабый первый прогон пометил задачу битой
(`content_status='needs_fix'`), а `battle_queryset()` с 04.09 фильтрует
`content_status = OK`, и из-за пометки задачу не пускает сильный прогон.
Из 1 740 задач допрогона в `needs_fix` сидят 1 736 — команда как есть молча
выбросила бы их, прогнала четыре и отчиталась об успехе.

Плюс к тому предупреждение врало: отброшенные id оно называло «фикстуры или
не существуют», хотя они существуют и не фикстуры.

Оба теста здесь, а не в `test_glm_enrich_run.py`, чтобы не разносить один
сюжет по полутора тысячам строк чужого файла.
"""
import io
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from problems.management.commands import glm_enrich_run as run_cmd
from problems.models import Problem, Source, SourceReference
from problems.tests.test_glm_enrich_run import (
    VALID_CALL2_JSON, _FakeReply, _valid_call1_json,
)


class ReadIdsFileTests(TestCase):
    """`--ids` принимается строкой через запятую, а 1 740 идентификаторов —
    около 10 КБ командной строки, при том что `cmd.exe` рвётся на 8 191
    символе, причём МОЛЧА обрезая."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def _write(self, text):
        path = self.tmp_dir / 'ids.txt'
        path.write_text(text, encoding='utf-8')
        return path

    def test_один_id_на_строку(self):
        self.assertEqual(run_cmd.read_ids_file(self._write('10\n20\n30\n')),
                         [10, 20, 30])

    def test_пустые_строки_и_комментарии_игнорируются(self):
        path = self._write('# манифест допрогона\n10\n\n  \n'
                           '20  # хвостовой комментарий\n#30\n40\n')
        self.assertEqual(run_cmd.read_ids_file(path), [10, 20, 40])

    def test_порядок_и_повторы_сохраняются_как_у_ids(self):
        """`--ids` не схлопывает дубли и не сортирует. Файл ведёт себя так же:
        иначе два способа задать одну выборку дали бы разные прогоны."""
        self.assertEqual(run_cmd.read_ids_file(self._write('30\n10\n30\n')),
                         [30, 10, 30])

    def test_нечисловая_строка_это_ошибка_а_не_молчаливый_пропуск(self):
        with self.assertRaises(CommandError) as ctx:
            run_cmd.read_ids_file(self._write('10\nдвадцать\n'))
        сообщение = str(ctx.exception)
        self.assertIn('двадцать', сообщение)
        self.assertIn('строка 2', сообщение)

    def test_нет_файла_это_ошибка(self):
        with self.assertRaises(CommandError):
            run_cmd.read_ids_file(self.tmp_dir / 'нет-такого.txt')

    def test_пустой_файл_это_ошибка(self):
        """Пустой манифест прошёл бы как «прогон на нуле задач» и отчитался
        бы об успехе — ровно тот класс ошибки, который эта сессия ловит."""
        with self.assertRaises(CommandError):
            run_cmd.read_ids_file(self._write('# только комментарий\n\n'))


class BattleQuerysetIncludeNonOkTests(TestCase):

    def setUp(self):
        self.ok = Problem.objects.create(statement='Годная.', content_status='ok')
        self.needs_fix = Problem.objects.create(
            statement='Битый текст.', content_status='needs_fix')
        self.junk = Problem.objects.create(statement='Мусор.', content_status='junk')
        fixture_source = Source.objects.create(name=run_cmd.SERVICE_FIXTURE_SOURCE)
        self.fixture = Problem.objects.create(statement='Служебная фикстура.')
        SourceReference.objects.create(problem=self.fixture, source=fixture_source)
        self.missing_id = 10 ** 7

    def test_без_флага_поведение_прежнее(self):
        ids = list(run_cmd.battle_queryset().values_list('id', flat=True))
        self.assertIn(self.ok.id, ids)
        self.assertNotIn(self.needs_fix.id, ids)
        self.assertNotIn(self.junk.id, ids)
        self.assertNotIn(self.fixture.id, ids)

    def test_с_флагом_content_status_не_фильтруется(self):
        ids = list(run_cmd.battle_queryset(include_nonok=True)
                   .values_list('id', flat=True))
        self.assertIn(self.ok.id, ids)
        self.assertIn(self.needs_fix.id, ids)
        self.assertIn(self.junk.id, ids)

    def test_с_флагом_служебные_фикстуры_всё_равно_исключены(self):
        """Флаг размыкает круг `content_status`, и только его. Фикстуры
        рендерера — не задачи вовсе, обогащать в них нечего."""
        ids = list(run_cmd.battle_queryset(include_nonok=True)
                   .values_list('id', flat=True))
        self.assertNotIn(self.fixture.id, ids)

    def test_причина_отказа_различает_три_случая(self):
        отказы = run_cmd.classify_rejected_ids(
            [self.ok.id, self.needs_fix.id, self.junk.id,
             self.fixture.id, self.missing_id], include_nonok=False)

        self.assertEqual(отказы['не существует'], [self.missing_id])
        self.assertEqual(отказы['служебная фикстура'], [self.fixture.id])
        self.assertEqual(отказы['исключена по content_status'],
                         sorted([self.needs_fix.id, self.junk.id]))

    def test_с_флагом_остаётся_только_две_причины(self):
        отказы = run_cmd.classify_rejected_ids(
            [self.ok.id, self.needs_fix.id, self.fixture.id, self.missing_id],
            include_nonok=True)

        self.assertEqual(отказы['не существует'], [self.missing_id])
        self.assertEqual(отказы['служебная фикстура'], [self.fixture.id])
        self.assertEqual(отказы['исключена по content_status'], [])


@override_settings(AI_PRICES={run_cmd.GLM_MODEL: run_cmd.GLM_PRICES_PROMO})
class IdsNonOkEndToEndTests(TestCase):
    """Главный инвариант фазы 1: «в прогон реально ушло 1 740 задач, а не
    четыре». Проверяется сквозняком, а не только на запросе."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.ok = Problem.objects.create(
            statement='Годная задача про рынок кофе.', content_status='ok')
        self.needs_fix = Problem.objects.create(
            statement='Задача про рынок кофе с битым текстом.',
            content_status='needs_fix')

    def _run(self, run_id, **kwargs):
        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(_valid_call1_json(user_text) if is_call1
                              else VALID_CALL2_JSON)

        parsed_out = self.tmp_dir / ('%s_parsed.jsonl' % run_id)
        buf = io.StringIO()
        with mock.patch.multiple(
                run_cmd,
                RAW_LOG_PATH=self.tmp_dir / 'run_raw.jsonl',
                PARSED_LOG_PATH=self.tmp_dir / 'run_parsed.jsonl',
                METRICS_PATH=self.tmp_dir / 'run_metrics.json',
                SAMPLE_MANIFEST_PATH=self.tmp_dir / 'sample.json',
                BATTLE_MANIFEST_PATH=self.tmp_dir / 'battle.json'), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn',
                                  return_value=fake_complete):
            call_command(
                'glm_enrich_run', max_cost=100.0, workers=1, run_id=run_id,
                raw_out=str(self.tmp_dir / ('%s_raw.jsonl' % run_id)),
                parsed_out=str(parsed_out),
                metrics_out=str(self.tmp_dir / ('%s_metrics.json' % run_id)),
                stdout=buf, **kwargs)

        строки = ([json.loads(s) for s in
                   parsed_out.read_text(encoding='utf-8').strip().splitlines()]
                  if parsed_out.exists() else [])
        return [r['problem_id'] for r in строки], buf.getvalue()

    def test_без_флага_needs_fix_отбрасывается_и_названа_причина(self):
        ids, вывод = self._run('nonok-off',
                               ids='%d,%d' % (self.ok.id, self.needs_fix.id))
        self.assertEqual(ids, [self.ok.id])
        self.assertIn('исключена по content_status', вывод)
        self.assertIn(str(self.needs_fix.id), вывод)

    def test_с_флагом_needs_fix_берётся_в_прогон(self):
        ids, _вывод = self._run('nonok-on', include_nonok=True,
                                ids='%d,%d' % (self.ok.id, self.needs_fix.id))
        self.assertEqual(sorted(ids), sorted([self.ok.id, self.needs_fix.id]))

    def test_ids_file_с_флагом_даёт_ту_же_выборку(self):
        path = self.tmp_dir / 'manifest.txt'
        path.write_text('# манифест допрогона\n%d\n%d\n'
                        % (self.ok.id, self.needs_fix.id), encoding='utf-8')
        ids, _вывод = self._run('nonok-file', include_nonok=True,
                                ids_file=str(path))
        self.assertEqual(sorted(ids), sorted([self.ok.id, self.needs_fix.id]))
