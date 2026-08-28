# -*- coding: utf-8 -*-
"""Импорт Школково в базу (Фаза 0 брифа import-new-sources).

Все четыре фикстуры — ЖИВЫЕ записи с диска, скопированные байт-в-байт
(`problems/tests/fixtures/shkolkovo/`), а не упрощённые примеры:

- 112523 — обычная задача без подпунктов, есть краткий ответ и решение;
- 112560 — подпункты а)/б) внутри `statement_tex`, краткий ответ прозой;
- 114064 — `\\includegraphics` в условии (картинка не докачана);
- 161520 — структурные `criteria_tex`, `source_name`, пустой `Answer.text`.
"""
import json
import os

from django.core.management import call_command
from django.test import TestCase
from io import StringIO

from problems.models import (
    Problem, ProblemPart, Rubric, RubricCriterion, Source, SourceReference,
)

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'shkolkovo')
SOURCE_NAME = 'Школково — банк задач по экономике'


def run(*args, **kwargs):
    out = StringIO()
    call_command('import_shkolkovo', *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


class ImportShkolkovoTests(TestCase):
    """Импорт четырёх живых задач Школково: INSERT, не UPDATE."""

    def test_dry_run_is_default_and_writes_nothing(self):
        """Без --apply команда обязана НИЧЕГО не создать (правило
        problems/management/commands/CLAUDE.md: боевой прогон — отдельный
        флаг, а не отсутствие --dry-run)."""
        run('--data-dir', FIXTURE_DIR)
        self.assertEqual(Problem.objects.count(), 0)
        self.assertEqual(Source.objects.count(), 0)

    def test_apply_creates_all_four_with_source(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertEqual(Problem.objects.count(), 4)
        source = Source.objects.get(name=SOURCE_NAME)
        # Source обязателен на КАЖДОЙ записи — 0 задач без ссылки.
        self.assertEqual(
            Problem.objects.exclude(source_references__source=source).count(), 0)
        self.assertEqual(SourceReference.objects.filter(source=source).count(), 4)

    def test_external_id_kept_and_import_is_idempotent(self):
        """Повторный --apply обязан дать ноль новых: id источника лежит в
        SourceReference.problem_number и служит ключом дедупликации."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        numbers = set(SourceReference.objects.values_list('problem_number', flat=True))
        self.assertEqual(numbers, {'112523', '112560', '114064', '161520'})

        second = run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertEqual(Problem.objects.count(), 4)
        self.assertIn('уже импортировано: 4', second)

    def test_subpoints_become_parts(self):
        """112560: а)/б) внутри statement_tex -> два ProblemPart, интро
        остаётся в statement задачи."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = Problem.objects.get(source_references__problem_number='112560')
        labels = list(problem.parts.order_by('order').values_list('label', flat=True))
        self.assertEqual(labels, ['а', 'б'])
        self.assertIn('Найдите равновесную цену', problem.parts.get(label='а').statement)
        self.assertNotIn('Найдите равновесную цену', problem.statement)
        self.assertIn('Q_d = 100 - 2P', problem.statement)

    def test_short_answer_and_title_taken_from_source(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = Problem.objects.get(source_references__problem_number='112560')
        self.assertEqual(problem.title, 'предкурс')
        self.assertIn('цена 16', problem.answer)
        self.assertTrue(problem.solution)

    def test_criteria_become_rubric(self):
        """161520: структурный criteria_tex -> Rubric + RubricCriterion."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = Problem.objects.get(source_references__problem_number='161520')
        rubric = Rubric.objects.get(problem=problem)
        self.assertGreaterEqual(rubric.criteria.count(), 3)
        self.assertTrue(
            RubricCriterion.objects.filter(rubric=rubric, max_points=1).exists())
        # source_name источника не теряется
        ref = SourceReference.objects.get(problem=problem)
        self.assertIn('Высшая проба', ref.note)

    def test_difficulty_is_null_because_source_has_no_signal(self):
        """DifficultyId у ВСЕХ 3414 задач Школково равен 0 — сигнала
        сложности в источнике нет. Выдумывать шкалу нельзя: поле остаётся
        пустым, метка источника — пустая строка."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        for problem in Problem.objects.all():
            self.assertIsNone(problem.difficulty)
            self.assertEqual(problem.difficulty_native, '')

    def test_content_hash_is_md5_of_stored_statement(self):
        """Нормализация ДО хэша: хэшируется то, что реально лежит в базе,
        иначе find_duplicates сравнивает разные тексты."""
        import hashlib
        run('--data-dir', FIXTURE_DIR, '--apply')
        for problem in Problem.objects.all():
            expected = hashlib.md5(
                problem.statement.encode('utf-8'), usedforsecurity=False).hexdigest()
            self.assertEqual(problem.content_hash, expected)

    def test_imported_as_draft_and_plain(self):
        """Источник не проверен человеком: draft + plain + скрыт до
        проверки. content_format='markdown' ставит только шлюз (Фаза 4)."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        for problem in Problem.objects.all():
            self.assertEqual(problem.status, Problem.Status.DRAFT)
            self.assertEqual(problem.content_format, Problem.ContentFormat.PLAIN)
            self.assertEqual(problem.human_review, '')
            self.assertTrue(problem.hidden_pending_review)

    def test_text_went_through_canonicalization(self):
        r"""Тот же конвейер, что у легаси: `\(...\)` схлопывается в `$...$`
        (math_canon), а `--` превращается в тире (core.normalize_dashes)."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = Problem.objects.get(source_references__problem_number='112560')
        self.assertNotIn('\\(', problem.statement)
        self.assertIn('$', problem.statement)
        self.assertNotIn(' -- ', problem.statement)

    def test_existing_problems_are_never_touched(self):
        """Свип-инвариант: импорт только вставляет. Ни у одной задачи,
        существовавшей ДО, не меняется ни текст, ни флаги."""
        old = Problem.objects.create(
            statement='Старое условие', answer='42', solution='старое решение',
            human_review=Problem.HumanReview.APPROVED,
            content_format=Problem.ContentFormat.MARKDOWN,
        )
        snapshot = (old.statement, old.answer, old.solution,
                    old.human_review, old.content_format)
        run('--data-dir', FIXTURE_DIR, '--apply')
        old.refresh_from_db()
        self.assertEqual(
            (old.statement, old.answer, old.solution,
             old.human_review, old.content_format), snapshot)
        self.assertEqual(Problem.objects.count(), 5)

    def test_limit_stops_the_import(self):
        """--limit обязан быть ЯВНО назван в выводе: молчаливое усечение
        читается как «импортировали всё»."""
        output = run('--data-dir', FIXTURE_DIR, '--apply', '--limit', '2')
        self.assertEqual(Problem.objects.count(), 2)
        self.assertIn('--limit 2', output)

    def test_missing_data_dir_fails_loudly(self):
        """Пустая/несуществующая папка обязана падать, а не печатать
        «прочитано 0»: ровно так corpus_pilot_shkolkovo молча прочитал 0
        задач в worktree, потому что путь считается от BASE_DIR."""
        from django.core.management.base import CommandError
        missing = os.path.join(FIXTURE_DIR, 'нет-такой-папки')
        with self.assertRaises(CommandError) as ctx:
            run('--data-dir', missing, '--apply')
        # Сообщение обязано назвать саму папку и переменную окружения —
        # иначе «прочитано 0» читается как «в источнике пусто».
        self.assertIn(missing, str(ctx.exception))
        self.assertIn('WECONOMICS_DATA_DIR', str(ctx.exception))


class ShkolkovoParityTests(TestCase):
    """Фикстуры не разошлись с диском: если файл на диске поменяется,
    тест обязан покраснеть, а не тихо проверять устаревшую копию."""

    def test_fixtures_are_verbatim_copies(self):
        disk_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            '..', 'weconomics-data', 'shkolkovo', 'problems')
        if not os.path.isdir(disk_dir):
            self.skipTest('корпус Школково недоступен на этой машине')
        for name in os.listdir(FIXTURE_DIR):
            with open(os.path.join(FIXTURE_DIR, name), encoding='utf-8') as f:
                fixture = json.load(f)
            with open(os.path.join(disk_dir, name), encoding='utf-8') as f:
                disk = json.load(f)
            self.assertEqual(fixture, disk, f'фикстура {name} разошлась с диском')
