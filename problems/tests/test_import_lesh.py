# -*- coding: utf-8 -*-
"""Импорт ЛЭШ_2026_Гамма в базу (Фаза 2 брифа import-new-sources).

Фикстура — два ЖИВЫХ файла архива, побайтовые копии:
`Подборки/Микроэкономика/Хотеллинг.tex` (5 задач) и
`Подборки/Микроэкономика/Хотеллинг Решалка.tex` (3 решения).

Форма фикстуры повторяет форму всего архива в миниатюре: у трёх задач
решение находится по точному совпадению `\\z[Название]`, у двух — нет.
Ровно это соотношение в полном архиве даёт 35 из 75. Задачи без решения
импортируются с ПУСТЫМ полем `solution` — угадывать по смыслу запрещено
брифом сессии.
"""
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from problems.models import Problem, Source, SourceReference

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'lesh')
SOURCE_NAME = 'ЛЭШ 2026 — Гамма'


#: Отчёты тестов уходят во ВРЕМЕННУЮ папку. Без этого прогон набора
#: писал в reports/import_new_sources/ репозитория и затирал настоящие
#: файлы — 933 предупреждения Школково превращались в четыре тестовых.
REPORT_DIR = tempfile.mkdtemp(prefix='qls-report-')


def run(*args, **kwargs):
    out = StringIO()
    call_command('import_lesh', *args, '--report-dir', REPORT_DIR,
                 stdout=out, stderr=out, **kwargs)
    return out.getvalue()


def by_name(fragment):
    return Problem.objects.get(source_references__note__contains=fragment)


class ImportLeshTests(TestCase):

    def test_dry_run_is_default_and_writes_nothing(self):
        run('--data-dir', FIXTURE_DIR)
        self.assertEqual(Problem.objects.count(), 0)
        self.assertEqual(Source.objects.count(), 0)

    def test_apply_creates_every_condition_with_source(self):
        """Все пять задач подборки, включая те, у которых решения нет."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertEqual(Problem.objects.count(), 5)
        source = Source.objects.get(name=SOURCE_NAME)
        self.assertEqual(
            Problem.objects.exclude(source_references__source=source).count(), 0)

    def test_matched_solution_is_imported(self):
        """«Классика» есть и в подборке, и в решалке — решение приезжает."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = by_name('Классика')
        self.assertTrue(problem.solution)
        self.assertIn('120', problem.solution)

    def test_unmatched_solution_stays_empty_not_guessed(self):
        """«Города и дороги» в решалке нет — поле пустое, и это осознанно:
        подбирать решение по смыслу в этой сессии запрещено."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = by_name('Города и дороги')
        self.assertEqual(problem.solution, '')

    def test_report_names_how_many_have_no_solution(self):
        """Молчаливое «импортировано 5» скрыло бы, что у двух пусто."""
        output = run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertIn('решение найдено по названию: 3', output)
        self.assertIn('без решения: 2', output)

    def test_subpoints_become_parts(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = by_name('Классика')
        self.assertEqual(problem.parts.count(), 2)
        self.assertEqual(
            list(problem.parts.order_by('order').values_list('label', flat=True)),
            ['1', '2'])

    def test_solution_subpoints_are_not_lost(self):
        """У решения «Классика» свои 4 пункта против 2 у условия — по
        частям их не разложить, но и выбросить нельзя: они дописываются
        в текст решения."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = by_name('Классика')
        self.assertGreater(problem.solution.count('\n'), 2)

    def test_no_difficulty_in_source(self):
        """У макроса \\z второй аргумент — БАЛЛЫ, а не сложность. Шкалы
        сложности у источника нет вовсе."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        for problem in Problem.objects.all():
            self.assertIsNone(problem.difficulty)
            self.assertEqual(problem.difficulty_native, '')

    def test_reference_note_keeps_file_and_name(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        ref = SourceReference.objects.get(problem=by_name('Классика'))
        self.assertIn('Хотеллинг.tex', ref.note)
        self.assertIn('Классика', ref.note)
        self.assertTrue(ref.problem_number)

    def test_import_is_idempotent(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        second = run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertEqual(Problem.objects.count(), 5)
        self.assertIn('уже импортировано: 5', second)

    def test_reshalka_file_is_not_imported_as_problems(self):
        """Файл «... Решалка.tex» — источник решений, а не задач. Иначе в
        банке появились бы дубли-«задачи», состоящие из решения."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        for ref in SourceReference.objects.all():
            self.assertNotIn('Решалка', ref.note)

    def test_imported_as_draft_and_plain(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        for problem in Problem.objects.all():
            self.assertEqual(problem.status, Problem.Status.DRAFT)
            self.assertEqual(problem.content_format, Problem.ContentFormat.PLAIN)
            self.assertTrue(problem.hidden_pending_review)

    def test_existing_problems_are_never_touched(self):
        old = Problem.objects.create(
            statement='Старое условие', human_review=Problem.HumanReview.APPROVED)
        run('--data-dir', FIXTURE_DIR, '--apply')
        old.refresh_from_db()
        self.assertEqual(old.statement, 'Старое условие')
        self.assertEqual(old.human_review, Problem.HumanReview.APPROVED)

    def test_missing_data_dir_fails_loudly(self):
        from django.core.management.base import CommandError
        missing = os.path.join(FIXTURE_DIR, 'нет-такой-папки')
        with self.assertRaises(CommandError) as ctx:
            run('--data-dir', missing, '--apply')
        self.assertIn(missing, str(ctx.exception))
