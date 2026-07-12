# -*- coding: utf-8 -*-
"""
Тесты import_vsosh_region: план без записи, боевой режим на мини-фикстуре,
отсев дубликатов по нормализованному условию.
"""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from problems.models import Problem, ProblemPart, Source, SourceReference

FIXTURE = {
    'year': 2023,
    'stage': 'региональный',
    'pdf_urls': {'9': 'https://example.org/9.pdf',
                 '11': 'https://example.org/11.pdf'},
    'unparsed': [],
    'questions': [
        {'grades': [9, 10], 'number': '1.1', 'qtype': 'boolean',
         'statement': 'Спрос всегда убывает по цене.', 'options': [],
         'correct': False, 'unit': '', 'solution': 'Бывают товары Гиффена.',
         'points': 1},
        {'grades': [11], 'number': '2.1', 'qtype': 'single',
         'statement': 'Что растёт при инфляции?',
         'options': ['Цены', 'Луна', 'Экспорт', 'Импорт'],
         'correct': 0, 'unit': '', 'solution': 'Определение инфляции.',
         'points': 3},
        {'grades': [9], 'number': '3.1', 'qtype': 'multi',
         'statement': 'Выберите факторы производства.',
         'options': ['Труд', 'Зарплата', 'Капитал', 'Цена'],
         'correct': [0, 2], 'unit': '', 'solution': '', 'points': 5},
        {'grades': [9, 10, 11], 'number': '4.1', 'qtype': 'numeric',
         'statement': 'Найдите равновесную цену при D=100-P, S=P.',
         'options': [], 'correct': '50', 'unit': '',
         'solution': '100-P=P, P=50.', 'points': 7},
    ],
}


def write_fixture(questions=None):
    data = dict(FIXTURE)
    if questions is not None:
        data['questions'] = questions
    f = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                    encoding='utf-8')
    json.dump(data, f, ensure_ascii=False)
    f.close()
    return f.name


class ImportVsoshPlanTests(TestCase):
    """Режим плана (без --confirm): считает, но не пишет."""

    def test_plan_writes_nothing(self):
        out = StringIO()
        call_command('import_vsosh_region', '--year', '2023',
                     '--file', write_fixture(), stdout=out)
        self.assertEqual(Problem.objects.count(), 0)
        self.assertEqual(Source.objects.count(), 0)
        text = out.getvalue()
        self.assertIn('Будет создано Problem: 4', text)
        # boolean 2 + single 4 + multi 4 + numeric 0
        self.assertIn('Будет создано ProblemPart (вариантов): 10', text)
        self.assertIn('НИЧЕГО не записано', text)

    def test_duplicate_by_normalized_statement(self):
        # та же данетка, но с другими пробелами и регистром — дубликат
        Problem.objects.create(
            title='', statement='спрос ВСЕГДА  убывает по цене.',
            problem_type='тест: верно/неверно', status='published')
        out = StringIO()
        call_command('import_vsosh_region', '--year', '2023',
                     '--file', write_fixture(), stdout=out)
        text = out.getvalue()
        self.assertIn('Будет создано Problem: 3', text)
        self.assertIn('Отсеяно как дубликаты по условию: 1', text)


class ImportVsoshConfirmTests(TestCase):
    """Боевой режим на мини-фикстуре."""

    @classmethod
    def setUpTestData(cls):
        out = StringIO()
        call_command('import_vsosh_region', '--year', '2023',
                     '--file', write_fixture(), '--confirm', stdout=out)

    def test_source_and_counts(self):
        src = Source.objects.get(name='ВсОШ — региональный этап')
        self.assertEqual(src.kind, 'олимпиада')
        self.assertEqual(Problem.objects.count(), 4)
        self.assertEqual(ProblemPart.objects.count(), 10)
        self.assertEqual(SourceReference.objects.count(), 4)

    def test_boolean_layout(self):
        p = Problem.objects.get(problem_type='тест: верно/неверно')
        self.assertEqual(p.answer, 'б')  # correct=False -> «Неверно»
        parts = list(p.parts.order_by('order'))
        self.assertEqual([x.statement for x in parts], ['Верно', 'Неверно'])
        self.assertEqual([x.answer for x in parts], ['неверно', 'верно'])
        self.assertEqual(p.status, 'published')

    def test_single_and_multi_letters(self):
        single = Problem.objects.get(problem_type='тест: один ответ')
        self.assertEqual(single.answer, 'а')
        multi = Problem.objects.get(problem_type='тест: все верные')
        self.assertEqual(multi.answer, 'ав')
        self.assertEqual(
            list(multi.parts.order_by('order').values_list('label', flat=True)),
            ['а', 'б', 'в', 'г'])

    def test_numeric_answer_and_reference(self):
        p = Problem.objects.get(problem_type='тест: числовой ответ')
        self.assertEqual(p.answer, '50')
        self.assertEqual(p.parts.count(), 0)
        ref = p.source_references.get()
        self.assertEqual(ref.stage, 'региональный')
        self.assertEqual(ref.year, 2023)
        self.assertEqual(ref.grade, '9, 10, 11')
        self.assertEqual(ref.problem_number, '4.1')
        self.assertEqual(ref.url, 'https://example.org/9.pdf')

    def test_rerun_skips_all_as_duplicates(self):
        out = StringIO()
        call_command('import_vsosh_region', '--year', '2023',
                     '--file', write_fixture(), stdout=out)
        self.assertIn('Будет создано Problem: 0', out.getvalue())
        self.assertIn('Отсеяно как дубликаты по условию: 4', out.getvalue())
