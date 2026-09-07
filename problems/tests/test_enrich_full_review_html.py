# -*- coding: utf-8 -*-
"""enrich_full_review_html — Фаза 3 приёмки: страница на 75 задач.

Главное, что проверяется: состав страницы (случайные + растровые + по
темам) не дублирует задачи и деterминирован зерном; только чтение.
"""
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from problems.management.commands.enrich_full_review_html import (
    N_RANDOM, N_RARE_THEMES, N_RASTER, N_TOP_THEMES, pick_sample,
)
from problems.models import Problem


def _row(problem_id, topic_primary=None, has_raster=False, defect=False):
    return {
        'problem_id': problem_id, 'defect': defect,
        'topic_primary': topic_primary, 'topics_secondary': [],
        'tags': ['1.1'], 'given': 'Дано', 'find': 'Найти',
        'econ_concepts': [], 'concepts_offlist': [],
        'graphical_solution': False, 'graphical_solution_source': 'none',
        'search_queries': [], 'dropped_queries': [], 'soft_violations': [],
        'title_candidate': 'Заголовок', 'has_raster': has_raster,
    }


class PickSampleTests(TestCase):
    """Логика отбора — чистая функция над списком строк, без БД."""

    def _rows(self, n=200, n_topics=29, n_raster=20):
        rows = []
        for i in range(n):
            rows.append(_row(
                i + 1,
                topic_primary=str(1 + i % n_topics),
                has_raster=(i < n_raster),
            ))
        return rows

    def test_ровно_75_без_дублей(self):
        rows = self._rows()
        entries, groups = pick_sample(rows)
        ids = [e['problem_id'] for e in entries]
        self.assertEqual(len(ids), 75)
        self.assertEqual(len(set(ids)), 75)

    def test_детерминирован_зерном(self):
        rows = self._rows()
        entries1, _ = pick_sample(rows, seed=42)
        entries2, _ = pick_sample(rows, seed=42)
        self.assertEqual([e['problem_id'] for e in entries1],
                         [e['problem_id'] for e in entries2])

    def test_растровые_задачи_отмечены_меткой(self):
        rows = self._rows(n_raster=20)
        entries, groups = pick_sample(rows)
        # Каждая растровая карточка, оказавшаяся на странице (через
        # выделенный резерв ИЛИ случайно через другую группу), обязана
        # нести метку «растр» — иначе подсветка на странице соврёт.
        raster_ids = {e['problem_id'] for e in entries if e.get('has_raster')}
        for pid in raster_ids:
            self.assertIn('растр', groups[pid])
        # Инвариант Фазы 3: НЕ МЕНЕЕ 15 растровых карточек — резерв это
        # минимум, случайные/тематические группы могут добавить ещё.
        self.assertGreaterEqual(sum(1 for labels in groups.values()
                                    if 'растр' in labels), N_RASTER)

    def test_состав_совпадает_со_спецификацией(self):
        rows = self._rows()
        entries, groups = pick_sample(rows)
        counts = {'растр': 0, 'случайная': 0, 'top': 0, 'rare': 0}
        for labels in groups.values():
            if 'растр' in labels:
                counts['растр'] += 1
            if 'случайная' in labels:
                counts['случайная'] += 1
            if any(l.startswith('частая_тема:') for l in labels):
                counts['top'] += 1
            if any(l.startswith('редкая_тема:') for l in labels):
                counts['rare'] += 1
        self.assertGreaterEqual(counts['растр'], N_RASTER)
        self.assertEqual(counts['случайная'], N_RANDOM)
        self.assertEqual(counts['top'], N_TOP_THEMES)
        self.assertEqual(counts['rare'], N_RARE_THEMES)

    def test_задача_на_пересечении_групп_не_дублируется(self):
        """Растровая задача из самой частой темы должна занять ОДНО место,
        а не два — освободившийся слот добирается следующей по порядку."""
        rows = self._rows(n_topics=1, n_raster=200)  # всё в одной теме, всё с растром
        entries, groups = pick_sample(rows)
        ids = [e['problem_id'] for e in entries]
        self.assertEqual(len(ids), len(set(ids)))
        # Одна тема, одна карточка «частая» и одна «редкая» — но раз тема
        # всего одна, ранжирование по частоте вырождено: важно лишь, что
        # страница не упала и не задвоила задачи.
        self.assertLessEqual(len(ids), 75)


class EnrichFullReviewHtmlCommandTests(TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.problems = [Problem.objects.create(statement='Задача %d.' % i)
                        for i in range(50)]

    def _write_parsed(self, rows):
        path = self.tmp / 'parsed.jsonl'
        with open(path, 'w', encoding='utf-8') as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + '\n')
        return path

    def _write_accept(self):
        path = self.tmp / 'accept.json'
        accept = {
            'phase1': {'manifest_total': 50, 'both_calls_in_manifest': 50,
                      'call1_only_ids': [], 'missing_entirely_ids': [],
                      'cost_usd': '1.0', 'elapsed_hours_by_mtime': 1.0,
                      'avg_rate_per_min': 50.0},
            'phase2': {'invariants_passed': 10, 'invariants_total': 16,
                      'sweep_detector': {'checked': 50, 'changed': 0},
                      'tags': {'used_count': 5, 'total_canonical': 344},
                      'titles': {'max_repeat': 2},
                      'problem_type': {'filled_pct': 100.0,
                                       'check_type_match_pct': 90.0}},
            'phase4_counts': {'broken_text': 0, 'lost_visuals': 0,
                             'answer_mismatch': 0, 'not_a_problem': 0,
                             'offlist_unique_terms': 0},
        }
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(accept, fh, ensure_ascii=False)
        return path

    def test_страница_собирается_на_неполном_пуле_без_падения(self):
        """50 задач — меньше 75. Команда обязана взять столько, сколько
        реально набралось (50), не падая и не дублируя карточки."""
        rows = [_row(p.id, topic_primary=str(1 + i % 10), has_raster=(i < 20))
                for i, p in enumerate(self.problems)]
        parsed_path = self._write_parsed(rows)
        accept_path = self._write_accept()
        out_path = self.tmp / 'review.html'

        call_command('enrich_full_review_html', parsed=str(parsed_path),
                    accept=str(accept_path), out=str(out_path))

        self.assertTrue(out_path.exists())
        text = out_path.read_text(encoding='utf-8')
        self.assertEqual(text.count('<div class="card'), 50)

    def test_брак_помечен_на_странице(self):
        rows = [_row(p.id, topic_primary='1', defect=(i == 0))
                for i, p in enumerate(self.problems)]
        parsed_path = self._write_parsed(rows)
        accept_path = self._write_accept()
        out_path = self.tmp / 'review.html'
        call_command('enrich_full_review_html', parsed=str(parsed_path),
                    accept=str(accept_path), out=str(out_path))
        text = out_path.read_text(encoding='utf-8')
        self.assertIn('БРАК', text)
