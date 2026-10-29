"""Импорт комплектов пакета олимпиад (`import_olympiads_kits`, ADR 0169).

Пакет собирается во временной папке из крошечных комплектов: тесты не
зависят от настоящего пакета (1,6 ГБ), но читают его тем же кодом.
"""
import hashlib
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from olympiads import kits_import as ki
from olympiads.models import (
    Olympiad, OlympiadVariant, OlympiadVariantFile, OlympiadVariantGrade,
    TrainingAttempt,
)
from problems.models import OlympiadRef, Problem

from .test_models import make_olympiad


def make_task(ref_key='k:1', status='clean', answer='', test=None,
              solution='', criteria=''):
    return {
        'ref_key': ref_key, 'number': '1', 'task_variant': '', 'title': 'з',
        'max_score': None, 'statement_md': 'условие', 'answer': answer,
        'solution_md': solution, 'criteria_md': criteria, 'test': test,
        'quality': {'status': status, 'reasons': [], 'has_solution': False},
    }


def make_kit_data(kit_id='mosh-2023-final-9-v1', slug='mosh', stage='final',
                  season='2022/2023', grade='9', tasks=None, files=None,
                  **kwargs):
    data = {
        'kit_id': kit_id, 'olympiad': {'slug': slug, 'name': 'Олимпиада ' + slug},
        'subject': 'Экономика', 'season': season, 'year': 2023, 'stage': stage,
        'tour': None, 'grade': grade, 'variant': 'v1', 'region': None,
        'official_url': 'https://example.org/' + kit_id + '.pdf',
        'reference_version': 'v7.1', 'files': files or [], 'open_issues': [],
        'tasks': [make_task()] if tasks is None else tasks,
    }
    data.update(kwargs)
    return data


class PackageMixin:
    """Временная папка пакета и вызов команды."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def write_kit(self, data):
        slug = data['olympiad']['slug']
        folder = os.path.join(self.root, slug, 'kits')
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, data['kit_id'] + '.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False)

    def run_import(self, *extra):
        out = StringIO()
        with override_settings(BASE_DIR=self.root):
            call_command('import_olympiads_kits', self.root, *extra,
                         stdout=out)
        return out.getvalue()

    def import_kit(self, **kwargs):
        self.write_kit(make_kit_data(**kwargs))
        return self.run_import('--apply')


class GradeAndSeasonTests(PackageMixin, TestCase):

    def test_range_gives_exactly_two_grade_rows(self):
        self.import_kit(grade='10-11')
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual(
            list(kit.grades.values_list('grade', flat=True)), [10, 11])
        self.assertEqual(kit.grade_raw, '10-11')

    def test_all_gives_no_grade_rows_but_keeps_raw(self):
        self.import_kit(grade='all')
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual(kit.grades.count(), 0)
        self.assertEqual(kit.grade_raw, 'all')

    def test_season_is_shortened(self):
        self.import_kit(season='2022/2023')
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual(kit.season, '2022/23')

    def test_unknown_stage_fails_with_kit_id(self):
        self.write_kit(make_kit_data(kit_id='mosh-2023-semi-9-v1',
                                     stage='semifinal'))
        with self.assertRaises(CommandError) as ctx:
            self.run_import('--apply')
        self.assertIn('mosh-2023-semi-9-v1', str(ctx.exception))
        self.assertIn('semifinal', str(ctx.exception))
        self.assertEqual(OlympiadVariant.objects.count(), 0)


class CountersTests(PackageMixin, TestCase):

    def test_answer_counts_both_answer_and_test_key(self):
        tasks = [
            make_task('k:1', answer='42'),
            make_task('k:2', test={'kind': 'single', 'key': 'б'}),
            make_task('k:3'),
            make_task('k:4', answer='  ', test={'kind': 'single', 'key': ''}),
        ]
        self.import_kit(tasks=tasks)
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual(kit.tasks_with_answer, 2)
        self.assertEqual(kit.tasks_total, 4)

    def test_criteria_and_solution_counters_and_item_flag(self):
        tasks = [
            make_task('k:1', criteria='по 2 балла', solution='разбор'),
            make_task('k:2', criteria='   '),
            make_task('k:3', solution='разбор'),
        ]
        self.import_kit(tasks=tasks)
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual(kit.tasks_with_criteria, 1)
        self.assertEqual(kit.tasks_with_solution, 2)
        # Тот же признак, что поедет в `OlympiadVariantItem.has_criteria`.
        self.assertTrue(ki.task_flags(tasks[0])['has_criteria'])
        self.assertFalse(ki.task_flags(tasks[1])['has_criteria'])

    def test_clean_and_flagged_are_split(self):
        self.import_kit(tasks=[make_task('k:1'), make_task('k:2', 'flagged')])
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual((kit.tasks_clean, kit.tasks_flagged), (1, 1))

    def test_kit_with_all_tasks_flagged_is_hidden(self):
        self.import_kit(tasks=[make_task('k:1', 'flagged'),
                               make_task('k:2', 'flagged')])
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual(kit.visibility, OlympiadVariant.Visibility.HIDDEN)

    def test_kit_with_one_clean_task_is_published(self):
        self.import_kit(tasks=[make_task('k:1', 'flagged'), make_task('k:2')])
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual(kit.visibility, OlympiadVariant.Visibility.PUBLISHED)


class IdempotencyTests(PackageMixin, TestCase):

    def test_second_run_creates_and_changes_nothing(self):
        files = [{'kind': 'условия', 'url': 'https://example.org/a.pdf',
                  'official': True, 'sha256': 'a' * 64, 'size': 10,
                  'original_name': 'a.pdf', 'path': 'mosh/sources/a.pdf'}]
        self.write_kit(make_kit_data(grade='10-11', files=files))
        self.run_import('--apply')
        before = (OlympiadVariant.objects.count(),
                  OlympiadVariantGrade.objects.count(),
                  OlympiadVariantFile.objects.count())
        out = self.run_import('--apply')
        self.assertEqual(before, (OlympiadVariant.objects.count(),
                                  OlympiadVariantGrade.objects.count(),
                                  OlympiadVariantFile.objects.count()))
        self.assertIn('kits_unchanged', out)
        self.assertNotIn('kits_created', out)
        self.assertNotIn('kits_updated', out)
        self.assertNotIn('files_created', out)
        self.assertNotIn('grades_created', out)

    def test_changed_package_updates_in_place(self):
        self.import_kit(tasks=[make_task('k:1')])
        pk = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1').pk
        out = self.import_kit(tasks=[make_task('k:1'), make_task('k:2')])
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual((kit.pk, kit.tasks_total), (pk, 2))
        self.assertIn('kits_updated', out)

    def test_dry_run_writes_nothing(self):
        self.write_kit(make_kit_data())
        out = self.run_import()
        self.assertIn('СУХОЙ ПРОГОН', out)
        self.assertEqual(OlympiadVariant.objects.count(), 0)
        self.assertEqual(Olympiad.objects.count(), 0)


class SafetyTests(PackageMixin, TestCase):

    def test_kit_with_attempts_is_updated_not_recreated(self):
        self.import_kit(tasks=[make_task('k:1')])
        kit = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        attempt = TrainingAttempt.objects.create(
            variant=kit, session_key='s', started_at=timezone.now())
        self.import_kit(tasks=[make_task('k:1'), make_task('k:2')])
        kit_after = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual(kit_after.pk, kit.pk)
        self.assertTrue(TrainingAttempt.objects.filter(pk=attempt.pk).exists())

    def test_kit_gone_from_package_is_marked_not_deleted(self):
        self.import_kit(kit_id='mosh-2023-final-9-v1')
        self.import_kit(kit_id='mosh-2023-final-10-v1')
        # Второй запуск видит в пакете оба файла; убираем первый.
        os.remove(os.path.join(self.root, 'mosh', 'kits',
                               'mosh-2023-final-9-v1.json'))
        out = self.run_import('--apply')
        gone = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        kept = OlympiadVariant.objects.get(kit_key='mosh-2023-final-10-v1')
        self.assertTrue(gone.absent_in_last_import)
        self.assertFalse(kept.absent_in_last_import)
        self.assertIn('kits_marked_absent', out)

    def test_returning_kit_loses_absent_mark(self):
        self.import_kit(kit_id='mosh-2023-final-9-v1')
        self.import_kit(kit_id='mosh-2023-final-10-v1')
        path = os.path.join(self.root, 'mosh', 'kits',
                            'mosh-2023-final-9-v1.json')
        saved = open(path, encoding='utf-8').read()
        os.remove(path)
        self.run_import('--apply')
        open(path, 'w', encoding='utf-8').write(saved)
        self.run_import('--apply')
        self.assertFalse(OlympiadVariant.objects.get(
            kit_key='mosh-2023-final-9-v1').absent_in_last_import)

    def test_package_import_never_touches_problems(self):
        self.import_kit()
        self.assertEqual(Problem.objects.count(), 0)


class HideLegacyKitsTests(PackageMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.olympiad = make_olympiad('mosh')
        self.legacy = OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2022, ref_event_id='mosh-2022-final-9')

    def test_hides_legacy_and_leaves_package_kit_alone(self):
        self.write_kit(make_kit_data())
        out = self.run_import('--apply', '--hide-legacy-kits')
        self.legacy.refresh_from_db()
        package = OlympiadVariant.objects.get(kit_key='mosh-2023-final-9-v1')
        self.assertEqual(self.legacy.visibility,
                         OlympiadVariant.Visibility.HIDDEN)
        self.assertEqual(package.visibility,
                         OlympiadVariant.Visibility.PUBLISHED)
        self.assertIn('mosh-2022-final-9', out)

    def test_without_flag_legacy_stays_published(self):
        self.write_kit(make_kit_data())
        self.run_import('--apply')
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.visibility,
                         OlympiadVariant.Visibility.PUBLISHED)

    def test_dry_run_shows_but_does_not_hide(self):
        self.write_kit(make_kit_data())
        out = self.run_import('--hide-legacy-kits')
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.visibility,
                         OlympiadVariant.Visibility.PUBLISHED)
        self.assertIn('mosh-2022-final-9', out)

    def test_does_not_delete_olympiad_refs_or_the_kit(self):
        problem = Problem.objects.create(title='з', statement='условие')
        OlympiadRef.objects.create(
            problem=problem, source_site='solvehub', olympiad_slug='mosh',
            event_id='mosh-2022-final-9', record_id='r1')
        self.write_kit(make_kit_data())
        self.run_import('--apply', '--hide-legacy-kits')
        self.assertEqual(OlympiadRef.objects.count(), 1)
        self.assertTrue(OlympiadVariant.objects.filter(
            pk=self.legacy.pk).exists())

    def test_second_run_hides_nothing_new(self):
        self.write_kit(make_kit_data())
        self.run_import('--apply', '--hide-legacy-kits')
        out = self.run_import('--apply', '--hide-legacy-kits')
        self.assertIn('legacy_kits_hidden_now       0', out)


class FilesTests(PackageMixin, TestCase):

    def make_pdf(self, content=b'%PDF-test'):
        rel = 'mosh/sources/mosh-2023-final-9-v1/aaaaaaaa_a.pdf'
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as fh:
            fh.write(content)
        return rel, hashlib.sha256(content).hexdigest()

    def files_for(self, rel, sha):
        return [{'kind': 'условия', 'url': 'https://example.org/a.pdf',
                 'official': True, 'sha256': sha, 'size': 9,
                 'original_name': 'a.pdf', 'path': rel}]

    def test_file_is_copied_and_checked(self):
        rel, sha = self.make_pdf()
        self.write_kit(make_kit_data(files=self.files_for(rel, sha)))
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        with override_settings(MEDIA_ROOT=media.name):
            self.run_import('--apply', '--files')
            row = OlympiadVariantFile.objects.get()
            self.assertTrue(os.path.isfile(os.path.join(media.name, row.file.name)))
            self.assertEqual(
                row.file.name,
                'olympiads/mosh/mosh-2023-final-9-v1/aaaaaaaa_a.pdf')

    def test_bad_sha_is_reported_and_not_copied(self):
        rel, _ = self.make_pdf()
        self.write_kit(make_kit_data(files=self.files_for(rel, 'f' * 64)))
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        with override_settings(MEDIA_ROOT=media.name):
            out = self.run_import('--apply', '--files')
        self.assertIn('files_bad_sha', out)
        self.assertEqual(OlympiadVariantFile.objects.get().file.name, '')
