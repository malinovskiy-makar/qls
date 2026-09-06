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
        # ⚠️ `note` здесь ОБЯЗАТЕЛЕН: льгота без дословной цитаты в
        # источнике не создаётся, и образец без неё ломал бы половину
        # тестов по причине, к их предмету не относящейся.
        self.write('sources.jsonl', [dict(
            key='s1', url='https://example.test/a', title='Источник',
            doc_type='order', note='Дословно: «льгота даётся победителям».')])
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

    def test_benefit_with_sourceless_quote_is_refused(self):
        """Ссылки мало — нужна дословная цитата.

        ⚠️ ЗАЧЕМ. Ссылка на правила приёма доказывает только то, что
        правила существуют. Проверить по ней запись человек не может:
        страница длинная и меняется каждый год. Цитата в `note` — это то,
        что он сверит глазами за минуту. Сессия 2 сохранила 48 льгот со
        ссылкой и БЕЗ цитаты, и часть из них оказалась просто неверной.
        """
        self.write('sources.jsonl', [dict(
            key='s1', url='https://example.test/a', title='Источник',
            doc_type='order')])                        # note пуст
        self.write('olympiads.jsonl', [dict(
            slug='vs', name_full='Тестовая', name_short='ТЕСТ',
            organizer='Никто', kind='vsosh', source='s1')])
        self.write('programs.jsonl', [dict(
            university_name='Вуз', university_short='ВУЗ',
            program_name='Экономика', order=1)])
        self.write('benefits.jsonl', [dict(
            slug='vs', program='ВУЗ', admission_year=2026,
            benefit_type='bvi', source='s1')])
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

    def test_only_one_file_still_resolves_source_keys(self):
        """⚠️ Найдено при заливке: `--only` терял ключи источников.

        Факты ссылаются на источник коротким ключом («hse-olimp»), а не
        адресом. Ключи брались из того же прогона, и заливка одного файла
        падала с «Льгота без источника» на данных, где источник есть.
        """
        self.base()
        call_command('import_olympiads_data', yes=True, only='sources.jsonl',
                     verbosity=0)
        call_command('import_olympiads_data', yes=True,
                     only='olympiads.jsonl', verbosity=0)
        self.assertEqual(Olympiad.objects.get(slug='vs').source.url,
                         'https://example.test/a')

    def test_dry_plan_writes_nothing(self):
        self.base()
        call_command('import_olympiads_data', verbosity=0)
        self.assertEqual(Olympiad.objects.count(), 0)
        self.assertEqual(UniversityProgram.objects.count(), 0)


class MissingOlympiadTests(ImportTestCase):
    """Льгота настоящей олимпиады, которой ещё нет в olympiads.jsonl
    (06.09.2026: «Финатлон» в перечне Финуниверситета), не роняет заливку и
    не выдумывается: строка пропускается, а в отчёте команды о ней написано."""

    def _benefits(self):
        self.write('programs.jsonl', [dict(
            university_short='ФУ', university_name='Финансовый университет',
            program_name='Экономика', city='Москва', order=1)])
        self.write('benefits.jsonl', [
            dict(slug='vs', program='ФУ', admission_year=2026, benefit_type='bvi',
                 required_level=3, source='s1'),
            dict(slug='finat', program='ФУ', admission_year=2026, benefit_type='bvi',
                 required_level=3, source='s1'),
        ])

    def test_benefit_of_unknown_olympiad_is_skipped_with_a_warning(self):
        from io import StringIO
        self.base()
        self._benefits()
        out = StringIO()
        call_command('import_olympiads_data', yes=True, stdout=out)
        self.assertEqual(OlympiadBenefit.objects.count(), 1)
        self.assertEqual(OlympiadBenefit.objects.get().olympiad.slug, 'vs')
        self.assertIn('ПРОПУЩЕНО', out.getvalue())
        self.assertIn('finat', out.getvalue())


class WipeTests(ImportTestCase):
    """`--wipe` сносит записи раздела (демо-данные) перед заливкой настоящих,
    источники остаются; список удаления — общий с seed_olympiads_demo."""

    def test_wipe_removes_demo_rows_before_import(self):
        call_command('seed_olympiads_demo', yes=True, verbosity=0)
        self.assertTrue(Olympiad.objects.filter(is_placeholder=True).exists())
        self.base()
        call_command('import_olympiads_data', yes=True, wipe=True, verbosity=0)
        self.assertEqual(list(Olympiad.objects.values_list('slug', flat=True)), ['vs'])
        self.assertFalse(Olympiad.objects.filter(is_placeholder=True).exists())
        self.assertTrue(FactSource.objects.filter(url='https://example.test/a').exists())
