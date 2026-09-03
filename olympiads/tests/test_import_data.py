"""Заливка собранных фактов: правила раздела обязаны держаться и здесь."""
import json
import pathlib
import tempfile
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase

from olympiads.models import (FactSource, Olympiad, OlympiadBenefit,
                              OlympiadEvent, OlympiadLevelYear,
                              UniversityProgram)

MODULE = 'olympiads.management.commands.import_olympiads_data'


class ImportTestCase(TestCase):
    """Общее: подменяем каталог JSONL временным."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        patcher = patch(MODULE + '.OUT_DIR', self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, rows):
        (self.dir / name).write_text(
            '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n',
            encoding='utf-8')

    def base(self):
        self.write('sources.jsonl', [dict(
            key='s1', url='https://example.test/a', title='Источник',
            doc_type='order')])
        self.write('olympiads.jsonl', [dict(
            slug='vs', name_full='Тестовая', name_short='ТЕСТ',
            organizer='Никто', kind='vsosh', source='s1')])


class DateRuleTests(ImportTestCase):
    """⚠️ Неподтверждённая дата не имеет права быть конкретной ([ADR 0064]).

    Правило живёт в `clean()` модели, и импорт обязан об него ЛОМАТЬСЯ.
    Иначе достаточно одной строки в файле сбора, чтобы на сайте появилось
    число, которого никто ещё не объявлял, — а школьник планирует по нему
    регистрацию.
    """

    def test_unconfirmed_date_with_a_number_is_rejected(self):
        self.base()
        self.write('events.jsonl', [dict(
            slug='vs', academic_year='2026/27', kind='stage',
            date_start='2027-01-20', date_status='awaiting',
            approx_text='обычно в январе', source='s1')])
        with self.assertRaises(ValidationError):
            call_command('import_olympiads_data', yes=True, verbosity=0)
        self.assertEqual(OlympiadEvent.objects.count(), 0)

    def test_confirmed_date_with_a_number_goes_through(self):
        self.base()
        self.write('events.jsonl', [dict(
            slug='vs', academic_year='2026/27', kind='stage',
            date_start='2027-01-20', date_status='confirmed', source='s1')])
        call_command('import_olympiads_data', yes=True, verbosity=0)
        self.assertEqual(OlympiadEvent.objects.count(), 1)


class BenefitSourceTests(ImportTestCase):
    """Льгота без источника не создаётся. По этой таблице подают документы."""

    def test_benefit_without_source_is_refused(self):
        self.base()
        self.write('programs.jsonl', [dict(
            university_name='Вуз', university_short='ВУЗ',
            program_name='Экономика', order=1)])
        self.write('benefits.jsonl', [dict(
            slug='vs', program='ВУЗ', admission_year=2026,
            benefit_type='bvi')])
        with self.assertRaises(CommandError):
            call_command('import_olympiads_data', yes=True, verbosity=0)
        self.assertEqual(OlympiadBenefit.objects.count(), 0)

    def test_benefit_with_source_is_created(self):
        self.base()
        self.write('programs.jsonl', [dict(
            university_name='Вуз', university_short='ВУЗ',
            program_name='Экономика', order=1)])
        self.write('benefits.jsonl', [dict(
            slug='vs', program='ВУЗ', admission_year=2026,
            benefit_type='bvi', source='s1')])
        call_command('import_olympiads_data', yes=True, verbosity=0)
        self.assertEqual(OlympiadBenefit.objects.count(), 1)


class IdempotencyTests(ImportTestCase):
    """Повторный запуск не плодит дубли — сбор рвётся и запускается снова."""

    def test_second_run_changes_nothing(self):
        self.base()
        self.write('levels.jsonl', [dict(
            slug='vs', academic_year='2025/26', level=2,
            approval_status='approved', source='s1')])
        call_command('import_olympiads_data', yes=True, verbosity=0)
        call_command('import_olympiads_data', yes=True, verbosity=0)
        self.assertEqual(Olympiad.objects.count(), 1)
        self.assertEqual(FactSource.objects.count(), 1)
        self.assertEqual(OlympiadLevelYear.objects.count(), 1)

    def test_import_clears_the_placeholder_flag(self):
        """Пришли настоящие данные — запись перестаёт быть заглушкой."""
        Olympiad.objects.create(slug='vs', name_full='Старое',
                                name_short='СТ', organizer='—',
                                kind='vsosh', is_placeholder=True)
        self.base()
        call_command('import_olympiads_data', yes=True, verbosity=0)
        self.assertFalse(Olympiad.objects.get(slug='vs').is_placeholder)

    def test_dry_plan_writes_nothing(self):
        self.base()
        call_command('import_olympiads_data', verbosity=0)
        self.assertEqual(Olympiad.objects.count(), 0)
        self.assertEqual(UniversityProgram.objects.count(), 0)
