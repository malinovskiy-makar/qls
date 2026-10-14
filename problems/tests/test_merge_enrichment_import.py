# -*- coding: utf-8 -*-
"""merge_enrichment_import: обогащение свежего импорта только в задачи своего журнала.

Две операции `merge_enrichment_v2` идут по всему банку (перевод старых
`problem_type` по таблице и кодовые особенности) — здесь они сужены до
журнала; существующие поля задачи (`title`, `problem_type`,
`content_status`) не перезаписываются, предложение модели уходит в CSV.
"""
import csv
import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from problems.enrich import layout
from problems.models import Problem, ProblemFeature


class MergeEnrichmentImportTests(TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.journal = self.tmp / 'run.jsonl'
        layout.ensure_features()
        self.own = Problem.objects.create(
            statement='Задача импорта.', answer='1', title='Задание 1',
            problem_type='задача с развёрнутым ответом', content_status='ok')
        # Чужая задача: старый тип из таблицы перевода и таблица в условии —
        # `merge_enrichment_v2` перевёл бы тип и поставил кодовую особенность.
        self.alien = Problem.objects.create(
            statement='| a | b |\n|---|---|\n| 1 | 2 |', answer='2',
            problem_type='тест: один ответ')
        with io.open(self.journal, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({
                'problem_id': self.own.id, 'title_candidate': 'Новое имя',
                'given': 'Дано из модели', 'task_nature': 'расчётная',
                'text_quality': 'серьёзные_дефекты',
            }, ensure_ascii=False) + '\n')

    def run_merge(self):
        protect = self.tmp / 'protected.csv'
        call_command('merge_enrichment_import', '--apply', parsed=str(self.journal),
                     protect_out=str(protect), out=str(self.tmp / 'out.json'),
                     sample_html=str(self.tmp / 'sample.html'), verbosity=0,
                     stdout=io.StringIO())
        return protect

    def test_alien_problem_untouched(self):
        self.run_merge()
        self.alien.refresh_from_db()
        self.assertEqual(self.alien.problem_type, 'тест: один ответ')
        self.assertFalse(ProblemFeature.objects.filter(problem=self.alien).exists())

    def test_existing_fields_protected_new_fields_filled(self):
        protect = self.run_merge()
        self.own.refresh_from_db()
        self.assertEqual(self.own.content_status, 'ok')
        self.assertEqual(self.own.problem_type, 'задача с развёрнутым ответом')
        self.assertEqual(self.own.title, 'Задание 1')
        self.assertEqual(self.own.title_candidate, 'Новое имя')
        self.assertEqual(self.own.given, 'Дано из модели')
        with open(protect, encoding='utf-8-sig') as h:
            rows = list(csv.DictReader(h))
        self.assertIn(('content_status', 'needs_fix'),
                      {(r['поле'], r['предлагала модель']) for r in rows})
