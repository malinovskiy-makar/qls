# -*- coding: utf-8 -*-
"""glm_review_build — Фаза 5: собрать run300_review.html из готовых
run_parsed.jsonl. Только чтение — не бьёт по API."""
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from problems.models import Problem, ProblemFigure


def _parsed_row(problem_id, defect=False):
    return {
        'problem_id': problem_id, 'defect': defect,
        'topic_primary': '1', 'tags': ['1.1'], 'given': 'Дано',
        'find': 'Найти', 'graphical_solution': False,
        'graphical_solution_source': 'none', 'title_candidate': 'Заголовок',
    }


class GlmReviewBuildTests(TestCase):

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.main_path = self.tmp_dir / 'main.jsonl'
        self.supplement_path = self.tmp_dir / 'supplement.jsonl'
        self.out_path = self.tmp_dir / 'review.html'

        self.main_problems = [
            Problem.objects.create(statement='Легаси задача %d.' % i)
            for i in range(8)
        ]
        self.image_problems = []
        for i in range(3):
            p = Problem.objects.create(statement='Задача с картинкой %d.' % i)
            ProblemFigure.objects.create(
                problem=p, tikz_hash='img%d' % i, source_field='statement',
                content_type='image/png', image_data=b'\x89PNG\r\n\x1a\n' + b'0' * 20)
            self.image_problems.append(p)

        with open(self.main_path, 'w', encoding='utf-8') as fh:
            for p in self.main_problems:
                fh.write(json.dumps(_parsed_row(p.id)) + '\n')
        with open(self.supplement_path, 'w', encoding='utf-8') as fh:
            for p in self.image_problems:
                fh.write(json.dumps(_parsed_row(p.id)) + '\n')

    def test_страница_собирается_из_двух_файлов_с_картинками(self):
        call_command('glm_review_build', main=str(self.main_path), main_count=5,
                    supplement=str(self.supplement_path), supplement_count=3,
                    out=str(self.out_path))

        self.assertTrue(self.out_path.exists())
        text = self.out_path.read_text(encoding='utf-8')
        self.assertEqual(text.count('<div class="card">'), 8)  # 5 + 3
        self.assertEqual(text.count('data:image/png;base64,'), 3)
        for p in self.main_problems[:5]:
            self.assertIn('Задача #%d' % p.id, text)
        for p in self.image_problems:
            self.assertIn('Задача #%d' % p.id, text)
            self.assertIn('донабор', text)

    def test_без_донабора_работает_только_с_основным(self):
        call_command('glm_review_build', main=str(self.main_path), main_count=8,
                    out=str(self.out_path))
        text = self.out_path.read_text(encoding='utf-8')
        self.assertEqual(text.count('<div class="card">'), 8)

    def test_брак_помечен_в_карточке(self):
        with open(self.main_path, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(_parsed_row(self.main_problems[0].id, defect=True)) + '\n')
        call_command('glm_review_build', main=str(self.main_path), main_count=1,
                    out=str(self.out_path))
        text = self.out_path.read_text(encoding='utf-8')
        self.assertIn('БРАК', text)

    def test_prioritize_visual_гарантирует_картинки_в_первых_n(self):
        # Фаза 3.4 задания сессии 02.09 (третья пересъёмка): «первые N по
        # файлу» не гарантирует визуальный пласт — картинки в выборке
        # распределены неравномерно, ровно тот баг, что уже чинили в
        # Фазе 2 для порядка обработки. Одним файлом (без --supplement),
        # где картиночные задачи стоят ПОСЛЕДНИМИ по файлу.
        with open(self.main_path, 'w', encoding='utf-8') as fh:
            for p in self.main_problems:
                fh.write(json.dumps(_parsed_row(p.id)) + '\n')
            for p in self.image_problems:
                fh.write(json.dumps(_parsed_row(p.id)) + '\n')

        call_command('glm_review_build', main=str(self.main_path), main_count=4,
                    prioritize_visual=True, min_raster=3, out=str(self.out_path))
        text = self.out_path.read_text(encoding='utf-8')
        self.assertEqual(text.count('data:image/png;base64,'), 3)
        self.assertEqual(text.count('class="card has-raster"'), 3)
        for p in self.image_problems:
            self.assertIn('Задача #%d' % p.id, text)
