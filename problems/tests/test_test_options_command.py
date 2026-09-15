# -*- coding: utf-8 -*-
"""Команда `test_options_from_statement`: сухой прогон, запись, откат, повтор.

Правила `weco-content-integrity`: без флага база не меняется; запись — одной
транзакцией со снимком и инвариантами; откат возвращает условие побайтно и не
трогает правленое руками; второй `--apply` ничего не находит.
"""
import glob
import io
import os
import tempfile
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from catalog import testplay
from problems.models import Problem, ProblemPart
from problems.tests.factories import make_problem

SINGLE_TEXT = ('Кто устанавливает ключевую ставку в России?\n\nВарианты ответа:\n\n'
               '1. (a) Правительство Российской Федерации;\n'
               '2. (b) Центральный банк Российской Федерации;\n'
               '3. (c) Министерство финансов.')


class TestOptionsCommandTests(TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.report = os.path.join(tmp.name, 'report')
        self.single = make_problem(
            SINGLE_TEXT, problem_type='единственный_выбор',
            answer='2. (b) Центральный банк Российской Федерации;')
        self.multi = make_problem(
            'Что входит в ВВП по расходам?\n1) потребление\n2) инвестиции\n3) трансферты',
            problem_type='множественный_выбор', answer='12')
        self.boolean = make_problem(
            'Кривая Лаффера показывает неравенство доходов.',
            problem_type='верно_неверно', answer='Неверно')
        self.subquestions = make_problem(
            'Спрос Q = 10 - P.\n1. Найдите равновесие.\n2. Постройте график.',
            problem_type='единственный_выбор', answer='5')
        self.with_parts = make_problem('Уже размечено.\n1) да\n2) нет',
                                       problem_type='единственный_выбор', answer='1')
        ProblemPart.objects.create(problem=self.with_parts, label='а', statement='да',
                                   answer='', order=0)
        self.ids_file = os.path.join(tmp.name, 'ids.txt')
        with open(self.ids_file, 'w', encoding='utf-8') as handle:
            handle.write('# id\tпричина\n')
            for problem in (self.single, self.multi, self.boolean,
                            self.subquestions, self.with_parts):
                handle.write('%d\tварианты текстом в условии\n' % problem.pk)

    def run_command(self, *args):
        out = io.StringIO()
        call_command('test_options_from_statement', *args, ids_file=self.ids_file,
                     report=self.report, stdout=out)
        return out.getvalue()

    def statements(self):
        return dict(Problem.objects.values_list('pk', 'statement'))

    def snapshot(self):
        return glob.glob(os.path.join(self.report, 'snapshot_*.json'))[0]

    def test_dry_run_writes_nothing_and_reports(self):
        statements, parts = self.statements(), ProblemPart.objects.count()
        out = self.run_command()
        self.assertEqual(self.statements(), statements)
        self.assertEqual(ProblemPart.objects.count(), parts)
        self.assertTrue('Сухой прогон' in out, 'нет пометки сухого прогона')
        with open(os.path.join(self.report, 'REPORT.md'), encoding='utf-8') as handle:
            report = handle.read()
        self.assertTrue('| `parsed` | 2 |' in report, 'разобраны не два теста')
        self.assertTrue('| `boolean_synthetic` | 1 |' in report, 'нет «верно/неверно»')
        self.assertTrue('| `verb_like_subquestion` | 1 |' in report, 'подвопросы не отклонены')
        self.assertTrue(os.path.exists(os.path.join(self.report, 'preview.html')))

    def test_apply_creates_parts_cuts_statement_and_widgets_live(self):
        self.run_command('--apply')
        single = Problem.objects.get(pk=self.single.pk)
        self.assertEqual(single.statement, 'Кто устанавливает ключевую ставку в России?')
        self.assertEqual(single.answer, '2. (b) Центральный банк Российской Федерации;')
        self.assertEqual(
            list(single.parts.order_by('order').values_list('label', 'statement', 'answer')),
            [('a', 'Правительство Российской Федерации', ''),
             ('b', 'Центральный банк Российской Федерации', 'верно'),
             ('c', 'Министерство финансов', '')])
        boolean = Problem.objects.get(pk=self.boolean.pk)
        self.assertEqual(boolean.statement, 'Кривая Лаффера показывает неравенство доходов.')
        self.assertEqual(
            list(boolean.parts.order_by('order').values_list('label', 'statement', 'answer')),
            [('а', 'Верно', ''), ('б', 'Неверно', 'верно')])
        for pk in (self.single.pk, self.multi.pk, self.boolean.pk):
            problem = Problem.objects.prefetch_related('parts').get(pk=pk)
            self.assertIsNotNone(testplay.game_of(problem), 'виджет не собрался у %d' % pk)
        self.assertFalse(Problem.objects.get(pk=self.subquestions.pk).parts.exists())

    def test_revert_restores_bytes_deletes_parts_and_candidates_return(self):
        statements, parts = self.statements(), ProblemPart.objects.count()
        self.run_command('--apply')
        self.run_command('--revert', self.snapshot())
        self.assertEqual(self.statements(), statements)
        self.assertEqual(ProblemPart.objects.count(), parts)
        self.assertTrue('к записи: задач 3' in self.run_command(),
                        'после отката кандидаты не те же')

    def test_second_apply_finds_nothing(self):
        self.run_command('--apply')
        parts = ProblemPart.objects.count()
        out = self.run_command('--apply')
        self.assertEqual(ProblemPart.objects.count(), parts)
        self.assertTrue('к записи: задач 0' in out, 'повторный --apply нашёл кандидатов')

    def test_revert_keeps_a_part_edited_by_hand(self):
        self.run_command('--apply')
        part = ProblemPart.objects.get(problem=self.single, label='a')
        part.statement = 'Правительство (правка методиста)'
        part.save()
        out = self.run_command('--revert', self.snapshot())
        self.assertTrue(ProblemPart.objects.filter(pk=part.pk).exists())
        self.assertTrue(str(part.pk) in out, 'откат не назвал правленый подпункт')

    def test_dead_widget_rolls_back_the_whole_transaction(self):
        statements, parts = self.statements(), ProblemPart.objects.count()
        with mock.patch('catalog.testplay.game_of', return_value=None), \
                self.assertRaises(CommandError):
            self.run_command('--apply')
        self.assertEqual(self.statements(), statements)
        self.assertEqual(ProblemPart.objects.count(), parts)
