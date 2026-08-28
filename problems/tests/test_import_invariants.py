# -*- coding: utf-8 -*-
"""Числовые инварианты импорта (Фаза 3 брифа import-new-sources).

Импорт обязан быть чистой вставкой. Проверяется это не на словах, а
свипом по снимку, снятому ДО импорта: у каждой задачи и каждого
подпункта, существовавших до сессии, сверяется отпечаток текста и флагов.

Отдельно проверяется то, ради чего снимок и нужен: сам свип обязан
КРАСНЕТЬ, когда старую задачу правда тронули. Проверка, которая не умеет
покраснеть, доказывает только саму себя.
"""
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.models import Problem, ProblemPart, Source, SourceReference


def run(*args):
    out = StringIO()
    call_command('import_invariants_check', *args, stdout=out, stderr=out)
    return out.getvalue()


class ImportInvariantsTests(TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.baseline = os.path.join(self.tmp, 'baseline.json')
        self.source = Source.objects.create(name='Тестовый источник')
        self.old = Problem.objects.create(
            statement='Старое условие', answer='42', solution='старое решение',
            human_review=Problem.HumanReview.APPROVED,
            content_format=Problem.ContentFormat.MARKDOWN,
        )
        self.old_part = ProblemPart.objects.create(
            problem=self.old, label='а', statement='пункт а', answer='1', order=0)
        SourceReference.objects.create(problem=self.old, source=self.source)
        run('--save-baseline', self.baseline)

    def _import_one(self, **kwargs):
        problem = Problem.objects.create(
            statement=kwargs.pop('statement', 'Новое условие'), **kwargs)
        if kwargs.pop('with_source', True):
            SourceReference.objects.create(
                problem=problem, source=self.source, problem_number='1')
        return problem

    def test_baseline_records_every_problem_and_part(self):
        with open(self.baseline, encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data['counts']['Problem'], 1)
        self.assertEqual(len(data['problems']), 1)
        self.assertEqual(len(data['parts']), 1)

    def test_pure_insert_passes(self):
        self._import_one()
        output = run('--baseline', self.baseline)
        self.assertIn('изменено старых задач: 0', output)
        self.assertIn('новых задач: 1', output)
        self.assertIn('новых без Source: 0', output)

    def test_changed_statement_of_old_problem_is_caught(self):
        """Главный инвариант: текст существовавшей задачи не тронут."""
        self.old.statement = 'Кто-то переписал условие'
        self.old.save()
        with self.assertRaises(CommandError) as ctx:
            run('--baseline', self.baseline)
        self.assertIn(str(self.old.id), str(ctx.exception))

    def test_changed_human_review_of_old_problem_is_caught(self):
        self.old.human_review = Problem.HumanReview.DEFECT
        self.old.save()
        with self.assertRaises(CommandError):
            run('--baseline', self.baseline)

    def test_changed_content_format_of_old_problem_is_caught(self):
        self.old.content_format = Problem.ContentFormat.PLAIN
        self.old.save()
        with self.assertRaises(CommandError):
            run('--baseline', self.baseline)

    def test_changed_part_of_old_problem_is_caught(self):
        self.old_part.statement = 'подменённый пункт'
        self.old_part.save()
        with self.assertRaises(CommandError):
            run('--baseline', self.baseline)

    def test_deleted_old_problem_is_caught(self):
        """Импорт не удаляет. Пропавшая из базы старая задача — не «0
        изменённых», а отдельная, названная поимённо беда."""
        self.old.delete()
        with self.assertRaises(CommandError) as ctx:
            run('--baseline', self.baseline)
        self.assertIn('пропал', str(ctx.exception).lower())

    def test_new_problem_without_source_is_caught(self):
        """Source обязателен у каждой новой задачи."""
        Problem.objects.create(statement='Сирота без источника')
        with self.assertRaises(CommandError) as ctx:
            run('--baseline', self.baseline)
        self.assertIn('без Source', str(ctx.exception))

    def test_expected_total_is_checked_when_given(self):
        self._import_one()
        run('--baseline', self.baseline, '--expect-total', '2')
        with self.assertRaises(CommandError) as ctx:
            run('--baseline', self.baseline, '--expect-total', '3')
        self.assertIn('3', str(ctx.exception))

    def test_expected_new_per_source_is_checked(self):
        self._import_one()
        self._import_one()
        run('--baseline', self.baseline,
            '--expect-new', f'{self.source.name}=2')
        with self.assertRaises(CommandError):
            run('--baseline', self.baseline,
                '--expect-new', f'{self.source.name}=5')

    def test_check_is_read_only(self):
        before = (Problem.objects.count(), ProblemPart.objects.count())
        self._import_one()
        run('--baseline', self.baseline)
        run('--baseline', self.baseline)
        self.assertEqual(
            (Problem.objects.count(), ProblemPart.objects.count()),
            (before[0] + 1, before[1]))
