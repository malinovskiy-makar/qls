"""Правки банка дома на движке синхронизации (Фаза 3 сессии 17.09.2026).

Каждая команда: правило делает ровно то, что решил владелец, повторный
прогон пуст, откат возвращает прежнее.
"""
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from problems.enrich.title_rules import stub_flags
from problems.management.commands.parts_relabel_letters import letter_label
from problems.models import Problem, ProblemPart, Source, SourceReference, Tag
from problems.tests.factories import link_source, make_problem, make_source


class _Run(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_cmd(self, name, *args):
        out = StringIO()
        call_command(name, '--report', str(self.tmp / name), *args, stdout=out)
        return out.getvalue()

    def revert(self, name):
        snapshot = sorted((self.tmp / name).glob('snapshot_*.json'))[-1]
        call_command(name, '--revert', str(snapshot), stdout=StringIO())


class SourcesTidyTests(_Run):
    def test_rename_and_merge_lesh_into_ile(self):
        ile = make_source('ILE / iloveeconomics.ru')
        solvehub = make_source('SolveHub — банк задач по экономике')
        lesh = make_source('ЛЭШ 2026 — Гамма')
        p = make_problem('Условие ЛЭШ.')
        link_source(p, lesh, year=2026, problem_number='a773b1d0', note='Подборки\\x.tex')

        self.run_cmd('sources_tidy', '--apply')
        self.assertEqual(Source.objects.get(pk=ile.pk).name, 'ILE (iloveeconomics.ru)')
        self.assertEqual(Source.objects.get(pk=solvehub.pk).name, 'SolveHub – банк задач по экономике')
        ref = SourceReference.objects.get(problem=p)
        self.assertEqual((ref.source_id, ref.year, ref.problem_number, ref.url),
                         (ile.pk, 2026, 'a773b1d0', 'https://iloveeconomics.ru/'))
        self.assertTrue('слит в ILE 17.09' in Source.objects.get(pk=lesh.pk).note)
        self.assertTrue('Изменений нет.' in self.run_cmd('sources_tidy'))

        self.revert('sources_tidy')
        self.assertEqual(Source.objects.get(pk=ile.pk).name, 'ILE / iloveeconomics.ru')
        self.assertEqual(SourceReference.objects.get(problem=p).source_id, lesh.pk)


class TitlesFromCandidatesTests(_Run):
    def test_only_stubs_are_replaced(self):
        stub = make_problem('Фирма выпускает товар.', title='Олигополия. Задача 9',
                            title_candidate='Дуополия Штакельберга')
        good = make_problem('Монополист и две цены.', title='Демпинг или как снижение издержек ведёт к выпуску',
                            title_candidate='Демпинг в модели Курно')
        no_cand = make_problem('Условие.', title='Тест')
        self.run_cmd('titles_from_candidates', '--apply')
        self.assertEqual(Problem.objects.get(pk=stub.pk).title, 'Дуополия Штакельберга')
        self.assertEqual(Problem.objects.get(pk=good.pk).title, good.title)
        self.assertEqual(Problem.objects.get(pk=no_cand.pk).title, 'Тест')
        self.assertTrue('Изменений нет.' in self.run_cmd('titles_from_candidates'))
        self.revert('titles_from_candidates')
        self.assertEqual(Problem.objects.get(pk=stub.pk).title, 'Олигополия. Задача 9')


class StubFlagsTests(SimpleTestCase):
    def test_flags(self):
        self.assertTrue('code' in stub_flags('Question 189', 'A firm produces'))
        self.assertEqual(stub_flags('МЭ 2023 10-11 задача 5', 'Условие'), ['code'])
        self.assertTrue('code' in stub_flags('ВП отбор', 'Условие'))
        self.assertTrue('digits' in stub_flags('12.3', 'Условие'))
        self.assertTrue('ellipsis' in stub_flags('Функция спроса на товар…', 'Условие'))
        self.assertTrue('start' in stub_flags('Функция предложения некоторого товара линейна.',
                                              'Функция  предложения некоторого товара линейна. Найдите…'))
        self.assertEqual(stub_flags('Кривая Великого Гэтсби и неравенство', 'Робин Гуд'), [])
        self.assertEqual(stub_flags('', 'Условие'), [])


class TagsMergeLegacyTests(_Run):
    def test_equal_names_merge_nested_do_not(self):
        canon = Tag.objects.create(name='Стагфляция', slug='stag', kind='canonical')
        legacy = Tag.objects.create(name='стагфляция', slug='stag-old', kind='legacy')
        legacy2 = Tag.objects.create(name='Стагфляция ', slug='stag-old2', kind='legacy')
        nested = Tag.objects.create(name='монополия', slug='mono', kind='legacy')
        Tag.objects.create(name='Двусторонняя монополия', slug='bimono', kind='canonical')
        p = make_problem('Стагфляция и монополия.')
        p.tags.add(legacy, legacy2, nested)

        self.run_cmd('tags_merge_legacy', '--apply')
        self.assertEqual(sorted(p.tags.values_list('name', flat=True)), ['Стагфляция', 'монополия'])
        self.assertTrue(Tag.objects.filter(pk=legacy.pk, kind='legacy').exists())
        self.assertEqual(canon.problems.count(), 1)
        self.assertTrue('Изменений нет.' in self.run_cmd('tags_merge_legacy'))
        self.revert('tags_merge_legacy')
        self.assertEqual(sorted(p.tags.values_list('name', flat=True)),
                         ['Стагфляция ', 'монополия', 'стагфляция'])


class PartsRelabelTests(_Run):
    def _problem(self, labels, solution='', problem_type=''):
        p = make_problem('Условие с подпунктами.', solution=solution, problem_type=problem_type)
        for order, label in enumerate(labels):
            ProblemPart.objects.create(problem=p, label=label, order=order, answer='x')
        return p

    def labels(self, p):
        return list(p.parts.order_by('order').values_list('label', flat=True))

    def test_open_problems_without_digit_refs_get_letters(self):
        plain = self._problem(['1', '2)', '(3)'])
        with_ref = self._problem(['1', '2'], solution='Из 1) следует, что…')
        test = self._problem(['1', '2'], problem_type='единственный_выбор')
        self.run_cmd('parts_relabel_letters', '--apply')
        self.assertEqual(self.labels(plain), ['а', 'б)', '(в)'])
        self.assertEqual(self.labels(with_ref), ['1', '2'])
        self.assertEqual(self.labels(test), ['1', '2'])
        self.assertTrue('Изменений нет.' in self.run_cmd('parts_relabel_letters'))
        self.revert('parts_relabel_letters')
        self.assertEqual(self.labels(plain), ['1', '2)', '(3)'])

    def test_letter_label(self):
        self.assertEqual(letter_label('9'), 'и')
        self.assertEqual(letter_label('10'), 'к')
        self.assertIsNone(letter_label('а'))
        self.assertIsNone(letter_label('1.5'))
