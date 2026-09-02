"""
Тесты команды link_olympiad_refs — привязка задач банка к олимпиадам через
точное совпадение SourceReference.url с внешним экспортом (JSONL).
"""

import json
import os
import tempfile

from django.core.management import call_command
from django.test import TestCase

from problems.models import OlympiadRef
from problems.tests.factories import link_source, make_problem, make_source

MATCHING_URL = 'https://solvehub.app/econ/problems/86884017864114198238'
OTHER_URL = 'https://solvehub.app/econ/problems/99999999999999999999'


def write_export(rows):
    fh = tempfile.NamedTemporaryFile(
        mode='w', suffix='.jsonl', delete=False, encoding='utf-8')
    for row in rows:
        fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    fh.close()
    return fh.name


def make_row(**overrides):
    row = {
        'academic_year': '2006/07',
        'event_id': 'solvehub-vseros-2007-final-5-11-2ff08344934d-397',
        'grade': '5-11',
        'number': '2',
        'olympiad_slug': 'vseros',
        'record_id': 'solvehub:86884017864114198238:solvehub-vseros-2007-final',
        'source_site': 'solvehub',
        'source_url': MATCHING_URL,
        'stage': 'final',
        'variant': 'Задачи',
        'year': 2007,
        'tags_claimed_by_solvehub': ['Макроэкономика'],
    }
    row.update(overrides)
    return row


class LinkOlympiadRefsTests(TestCase):
    def setUp(self):
        self.source = make_source(name='SolveHub — банк задач по экономике')
        self.problem = make_problem(statement='Условие про ВВП и инфляцию.')
        link_source(self.problem, self.source, url=MATCHING_URL)

    def tearDown(self):
        for path in getattr(self, '_export_paths', []):
            if os.path.exists(path):
                os.remove(path)

    def export(self, rows):
        path = write_export(rows)
        self._export_paths = getattr(self, '_export_paths', []) + [path]
        return path

    def test_точное_совпадение_создаёт_olympiadref_с_правильными_полями(self):
        export_path = self.export([make_row()])

        call_command('link_olympiad_refs', export_path=export_path,
                    apply=True, verbosity=0)

        self.assertEqual(OlympiadRef.objects.count(), 1)
        ref = OlympiadRef.objects.get()
        self.assertEqual(ref.problem_id, self.problem.id)
        self.assertEqual(ref.source_site, 'solvehub')
        self.assertEqual(ref.olympiad_slug, 'vseros')
        self.assertEqual(ref.year, 2007)
        self.assertEqual(ref.stage, 'final')
        self.assertEqual(ref.grade, '5-11')
        self.assertEqual(ref.variant, 'Задачи')
        self.assertEqual(ref.number, '2')
        self.assertEqual(ref.event_id,
                         'solvehub-vseros-2007-final-5-11-2ff08344934d-397')
        self.assertEqual(ref.match_method, 'url_exact')
        self.assertEqual(ref.match_score, 1.0)
        self.assertEqual(ref.official_url, MATCHING_URL)
        self.assertIn('tags_claimed_by_solvehub', ref.raw_meta)

    def test_несовпадающий_url_не_создаёт_ничего(self):
        export_path = self.export([make_row(
            source_url=OTHER_URL,
            event_id='solvehub-other-event')])

        call_command('link_olympiad_refs', export_path=export_path,
                    apply=True, verbosity=0)

        self.assertEqual(OlympiadRef.objects.count(), 0)

    def test_повторный_apply_не_создаёт_дублей(self):
        export_path = self.export([make_row()])

        call_command('link_olympiad_refs', export_path=export_path,
                    apply=True, verbosity=0)
        call_command('link_olympiad_refs', export_path=export_path,
                    apply=True, verbosity=0)

        self.assertEqual(OlympiadRef.objects.count(), 1)

    def test_сухой_прогон_не_пишет_в_базу(self):
        export_path = self.export([make_row()])
        count_до = OlympiadRef.objects.count()

        call_command('link_olympiad_refs', export_path=export_path,
                    verbosity=0)

        self.assertEqual(OlympiadRef.objects.count(), count_до)
        self.assertEqual(OlympiadRef.objects.count(), 0)

    def test_www_нормализация_находит_совпадение_с_пониженным_score(self):
        db_url = 'https://www.iloveeconomics.ru/z/6246'
        export_url = 'https://iloveeconomics.ru/z/6246'  # без www — как в реальном экспорте
        ile_problem = make_problem(statement='Условие про эластичность спроса.')
        link_source(ile_problem, self.source, url=db_url)

        export_path = self.export([make_row(
            source_url=export_url,
            source_site='ile',
            event_id='ile-event-1',
            record_id='ile:record:1')])

        call_command('link_olympiad_refs', export_path=export_path,
                    apply=True, verbosity=0)

        ref = OlympiadRef.objects.get(problem=ile_problem)
        self.assertEqual(ref.match_method, 'url_www_normalized')
        self.assertEqual(ref.match_score, 0.97)
        # official_url — настоящий url ИЗ БАЗЫ, а не из экспорта (без www не сохраняется как истина).
        self.assertEqual(ref.official_url, db_url)

    def test_разные_домены_без_www_не_матчатся(self):
        """Страховка от слишком широкой нормализации: срезаем 'www.', но
        НЕ трогаем сам домен — example.com и example.org разные сайты."""
        link_source(self.problem, self.source, url='https://example.com/task/1')
        export_path = self.export([make_row(
            source_url='https://example.org/task/1',
            event_id='cross-domain-event')])

        call_command('link_olympiad_refs', export_path=export_path,
                    apply=True, verbosity=0)

        self.assertEqual(OlympiadRef.objects.count(), 0)
