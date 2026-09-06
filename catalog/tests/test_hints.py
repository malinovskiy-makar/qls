"""Фаза 6.1: подсказки уровнями — эндпоинт, кнопка, команда загрузки."""
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from problems.models import Hint, ProblemPart
from problems.tests.factories import make_problem, make_topic


class HintApiTests(TestCase):
    def setUp(self):
        self.problem = make_problem('Задача с подсказками.', topic=make_topic('Эластичность'))
        self.part = ProblemPart.objects.create(problem=self.problem, label='а',
                                               statement='Пункт а', order=1)
        Hint.objects.create(problem=self.problem, order=2, text='Вторая $E_d$', reviewed=True)
        Hint.objects.create(problem=self.problem, order=1, text='Первая', reviewed=True)
        Hint.objects.create(problem=self.problem, part=self.part, order=1,
                            text='К пункту а', generated_by_ai=True)
        self.page = reverse('catalog:problem_detail', args=[self.problem.pk])

    def _get(self, n):
        return self.client.get(reverse('catalog:api_hint', args=[self.problem.pk, n]))

    def test_three_hints_come_in_order_then_404(self):
        first = json.loads(self._get(1).content)
        self.assertEqual(first, {'n': 1, 'total': 3, 'text': 'Первая', 'ai': False,
                                 'reviewed': True, 'part': ''})
        self.assertEqual(json.loads(self._get(2).content)['text'], 'Вторая $E_d$')
        third = json.loads(self._get(3).content)
        self.assertEqual((third['text'], third['part'], third['ai'], third['reviewed']),
                         ('К пункту а', 'а', True, False))
        self.assertEqual(self._get(4).status_code, 404)
        self.assertEqual(self._get(0).status_code, 404)

    def test_button_only_when_there_are_hints(self):
        html = self.client.get(self.page).content.decode()
        self.assertIn('id="hint-btn"', html)
        self.assertIn('<span class="n" id="hint-n">1 из 3</span>', html)
        self.assertIn('"hintTotal": 3', html)
        self.assertIn('"hintUrl": "/catalog/api/hint/%d/"' % self.problem.pk, html)
        bare = make_problem('Без подсказок.')
        html = self.client.get(reverse('catalog:problem_detail', args=[bare.pk])).content.decode()
        self.assertNotIn('id="hint-btn"', html)
        self.assertNotIn('hintUrl', html)
        self.assertNotIn('id="hints"', html)

    def test_hidden_problem_gives_404(self):
        hidden = make_problem('Скрытая.', flagged=True)
        Hint.objects.create(problem=hidden, order=1, text='x')
        self.assertEqual(self.client.get(reverse('catalog:api_hint', args=[hidden.pk, 1])).status_code, 404)


class ImportHintsCommandTests(TestCase):
    def setUp(self):
        self.p1 = make_problem('Первая.')
        self.p2 = make_problem('Вторая.')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _file(self, rows, name='hints.jsonl'):
        path = os.path.join(self.tmp.name, name)
        with open(path, 'w', encoding='utf-8') as fh:
            for row in rows:
                fh.write((row if isinstance(row, str) else json.dumps(row, ensure_ascii=False)) + '\n')
        return path

    def _run(self, path, **opts):
        out = StringIO()
        call_command('import_hints', path, snapshot_dir=os.path.join(self.tmp.name, 'undo'),
                     stdout=out, **opts)
        return out.getvalue()

    def test_dry_run_creates_nothing(self):
        out = self._run(self._file([{'problem_id': self.p1.pk, 'hints': ['а', 'б', 'в'],
                                     'generated_by_ai': True}]))
        self.assertIn('Подсказок будет создано: 3 у 1 задач', out)
        self.assertIn('Сухой прогон', out)
        self.assertEqual(Hint.objects.count(), 0)

    def test_apply_creates_exactly_n_in_order_and_button_appears(self):
        page = reverse('catalog:problem_detail', args=[self.p1.pk])
        self.assertNotIn('id="hint-btn"', self.client.get(page).content.decode())
        out = self._run(self._file([{'problem_id': self.p1.pk, 'hints': ['а', 'б', 'в'],
                                     'generated_by_ai': True, 'reviewed': False}]), apply=True)
        self.assertIn('Записано: 3 подсказок у 1 задач', out)
        hints = list(Hint.objects.filter(problem=self.p1).order_by('order'))
        self.assertEqual([(h.order, h.text, h.generated_by_ai, h.reviewed) for h in hints],
                         [(1, 'а', True, False), (2, 'б', True, False), (3, 'в', True, False)])
        self.assertIn('1 из 3', self.client.get(page).content.decode())

    def test_second_run_without_replace_does_not_duplicate(self):
        path = self._file([{'problem_id': self.p1.pk, 'hints': ['а', 'б']}])
        self._run(path, apply=True)
        out = self._run(path, apply=True)
        self.assertIn('пропущены (уже есть подсказки, нужен --replace)', out)
        self.assertIn('Записывать нечего', out)
        self.assertEqual(Hint.objects.filter(problem=self.p1).count(), 2)

    def test_replace_swaps_hints_and_writes_a_snapshot(self):
        self._run(self._file([{'problem_id': self.p1.pk, 'hints': ['старая']}]), apply=True)
        out = self._run(self._file([{'problem_id': self.p1.pk, 'hints': ['новая 1', 'новая 2']}],
                                   name='new.jsonl'), apply=True, replace=True)
        self.assertIn('Записано: 2 подсказок у 1 задач', out)
        self.assertEqual(list(Hint.objects.filter(problem=self.p1).order_by('order')
                              .values_list('text', flat=True)), ['новая 1', 'новая 2'])
        undo = os.listdir(os.path.join(self.tmp.name, 'undo'))
        self.assertEqual(len(undo), 1)
        with open(os.path.join(self.tmp.name, 'undo', undo[0]), encoding='utf-8') as fh:
            self.assertEqual(json.loads(fh.readline())['hints'], ['старая'])

    def test_bad_lines_and_unknown_ids_are_reported_others_apply(self):
        out = self._run(self._file([
            {'problem_id': self.p1.pk, 'hints': ['ок']},
            {'problem_id': self.p2.pk, 'hints': []},
            {'problem_id': 987654321, 'hints': ['нет такой']},
            'мусор',
        ]), apply=True)
        self.assertIn('с ошибками: 2', out)
        self.assertIn('не найдено id: 1', out)
        self.assertIn('Записано: 1 подсказок у 1 задач', out)
        self.assertEqual(Hint.objects.count(), 1)

    def test_backfill_marks_existing_hints_reviewed(self):
        from django.apps import apps
        from importlib import import_module
        migration = import_module('problems.migrations.0053_hint_reviewed_backfill')
        human = Hint.objects.create(problem=self.p1, order=1, text='рукой')
        robot = Hint.objects.create(problem=self.p2, order=1, text='ИИ', generated_by_ai=True)
        migration.mark_reviewed(apps, None)
        human.refresh_from_db(); robot.refresh_from_db()
        self.assertTrue(human.reviewed)
        self.assertFalse(robot.reviewed)
