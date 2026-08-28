# -*- coding: utf-8 -*-
"""Импорт SolveHub в базу (Фаза 1 брифа import-new-sources).

Шесть фикстур — ЖИВЫЕ записи с диска, побайтовые копии, по одной на
каждый встречающийся `check_type` (седьмой, `matching_list`, в корпусе
один-единственный и покрыт юнит-тестом формата ответа):

- `00382383782316876614` (#12118) — `single_choice`, level1, 4 варианта;
- `06470742608655646922` (#10039) — `multiple_choice`, difficulty `none`;
- `14902373698778468776` (#12324) — `true_false`, level4, есть `source`;
- `00160353622325841791` (#5518)  — `single_freetext`, 4 написания ответа;
- `00009564927571502540` (#6371)  — `multiple_questions`, level3;
- `00227147538657087707` (#401)   — `multiple_choice` с картинкой в условии.
"""
import json
import os
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from problems.corpus_converter.solvehub import format_answer, parse_options
from problems.models import Problem, Source, SourceReference

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'solvehub')
SOURCE_NAME = 'SolveHub — банк задач по экономике'


def run(*args, **kwargs):
    out = StringIO()
    call_command('import_solvehub', *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


def by_id(external_id):
    return Problem.objects.get(source_references__problem_number=external_id)


class SolveHubAnswerFormatTests(TestCase):
    """Формат ответа по каждому типу проверки — без базы и без диска."""

    def test_single_choice_index_is_zero_based(self):
        """Ошибка на единицу здесь = неверный ответ у 1765 задач."""
        options = ['0%', '1%', '2%', '3%', '6%']
        answer = format_answer('{"type":"single_choice","value":3}', options)
        self.assertEqual(answer, '4. 3%')

    def test_single_choice_out_of_range_warns_and_stays_empty(self):
        warnings = []
        answer = format_answer('{"type":"single_choice","value":9}', ['а', 'б'], warnings)
        self.assertEqual(answer, '')
        self.assertTrue(warnings)

    def test_multiple_choice_lists_only_true_options(self):
        answer = format_answer(
            '{"type":"multiple_choice","value":[false,true,false,true]}',
            ['P = 85', 'P = 40', 'P = 60', 'P = 50'])
        self.assertEqual(answer, '2. P = 40\n4. P = 50')

    def test_true_false(self):
        self.assertEqual(format_answer('{"type":"true_false","value":true}', []), 'Верно')
        self.assertEqual(format_answer('{"type":"true_false","value":false}', []), 'Неверно')

    def test_single_freetext_keeps_all_accepted_spellings(self):
        answer = format_answer(
            '{"type":"single_freetext","value":["70,71","70,71%","70.71","70,71"]}', [])
        self.assertEqual(answer, '70,71 / 70,71% / 70.71')

    def test_multiple_questions_pairs_labels_with_values(self):
        answer = format_answer(
            '{"type":"multiple_questions","value":["21%","33,1%"]}',
            ['В краткосрочном периоде на', 'В долгосрочном периоде на'])
        self.assertEqual(
            answer, 'В краткосрочном периоде на 21%\nВ долгосрочном периоде на 33,1%')

    def test_matching_list_pairs_labels_with_values(self):
        answer = format_answer(
            '{"type":"matching_list","value":["экспортёр","импортёр"]}', ['A', 'B'])
        self.assertEqual(answer, 'A экспортёр\nB импортёр')

    def test_uncheckable_leaves_answer_empty(self):
        """2294 задачи корпуса — ответа в источнике нет. Выдумывать нечего."""
        self.assertEqual(format_answer('{"type":"uncheckable","value":null}', []), '')

    def test_unknown_type_warns_instead_of_guessing(self):
        warnings = []
        self.assertEqual(format_answer('{"type":"новый","value":1}', [], warnings), '')
        self.assertTrue(warnings)

    def test_parse_options_survives_broken_json(self):
        self.assertEqual(parse_options('не json'), [])
        self.assertEqual(parse_options(''), [])
        self.assertEqual(parse_options('["а","б"]'), ['а', 'б'])


class ImportSolveHubTests(TestCase):

    def test_dry_run_is_default_and_writes_nothing(self):
        run('--data-dir', FIXTURE_DIR)
        self.assertEqual(Problem.objects.count(), 0)
        self.assertEqual(Source.objects.count(), 0)

    def test_apply_creates_all_six_with_source(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertEqual(Problem.objects.count(), 6)
        source = Source.objects.get(name=SOURCE_NAME)
        self.assertEqual(
            Problem.objects.exclude(source_references__source=source).count(), 0)

    def test_difficulty_mapped_to_project_scale(self):
        """level1..level5 -> 1..5, none -> NULL; метка источника сохранена."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        easy = by_id('00382383782316876614')      # level1
        self.assertEqual(easy.difficulty, 1)
        self.assertEqual(easy.difficulty_native, 'level1')
        hard = by_id('14902373698778468776')      # level4
        self.assertEqual(hard.difficulty, 4)
        self.assertEqual(hard.difficulty_native, 'level4')
        none = by_id('06470742608655646922')      # none
        self.assertIsNone(none.difficulty)
        self.assertEqual(none.difficulty_native, '')

    def test_choice_options_land_in_statement(self):
        """Без вариантов ответа задача выбора не имеет смысла — они
        дописываются в условие списком (2241 задача корпуса)."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = by_id('06470742608655646922')
        self.assertIn('Варианты ответа:', problem.statement)
        self.assertIn('P = 85', problem.statement)
        self.assertIn('P = 50', problem.statement)

    def test_answer_built_from_correct_answer(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertEqual(by_id('06470742608655646922').answer, '2. P = 40\n4. P = 50')
        self.assertEqual(by_id('14902373698778468776').answer, 'Верно')
        self.assertIn('70,71', by_id('00160353622325841791').answer)

    def test_solution_comes_from_answer_md(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertTrue(by_id('00009564927571502540').solution)

    def test_images_stay_in_text_as_markdown(self):
        """Картинка остаётся ссылкой в тексте: FileAsset во всём банке пуст,
        показ картинок не подключён — это известное ограничение, а не повод
        выкинуть ссылку из условия."""
        run('--data-dir', FIXTURE_DIR, '--apply')
        problem = by_id('00227147538657087707')
        self.assertIn('![', problem.statement)

    def test_duplicates_are_not_filtered_out(self):
        """366 совпадений content_hash с банком признаны вероятно ложными
        (короткие типовые формулировки). Импорт их НЕ отбрасывает —
        find_duplicates разберётся позже своей обычной логикой."""
        first = json.load(open(
            os.path.join(FIXTURE_DIR, '14902373698778468776.json'), encoding='utf-8'))
        run('--data-dir', FIXTURE_DIR, '--apply')
        twin_hash = by_id('14902373698778468776').content_hash
        # заводим «чужую» задачу с тем же условием и импортируем заново
        Problem.objects.filter(
            source_references__problem_number='14902373698778468776').delete()
        Problem.objects.create(statement=first['md'], content_hash=twin_hash)
        run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertTrue(
            SourceReference.objects.filter(
                problem_number='14902373698778468776').exists())

    def test_import_is_idempotent(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        second = run('--data-dir', FIXTURE_DIR, '--apply')
        self.assertEqual(Problem.objects.count(), 6)
        self.assertIn('уже импортировано: 6', second)

    def test_imported_as_draft_and_plain(self):
        run('--data-dir', FIXTURE_DIR, '--apply')
        for problem in Problem.objects.all():
            self.assertEqual(problem.status, Problem.Status.DRAFT)
            self.assertEqual(problem.content_format, Problem.ContentFormat.PLAIN)
            self.assertTrue(problem.hidden_pending_review)

    def test_existing_problems_are_never_touched(self):
        old = Problem.objects.create(
            statement='Старое условие', answer='42',
            human_review=Problem.HumanReview.APPROVED)
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


class SolveHubParityTests(TestCase):

    def test_fixtures_are_verbatim_copies(self):
        disk_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            '..', 'weconomics-data', 'solvehub', 'problems')
        if not os.path.isdir(disk_dir):
            self.skipTest('корпус SolveHub недоступен на этой машине')
        for name in os.listdir(FIXTURE_DIR):
            with open(os.path.join(FIXTURE_DIR, name), encoding='utf-8') as f:
                fixture = json.load(f)
            with open(os.path.join(disk_dir, name), encoding='utf-8') as f:
                disk = json.load(f)
            self.assertEqual(fixture, disk, f'фикстура {name} разошлась с диском')
