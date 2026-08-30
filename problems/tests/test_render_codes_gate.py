# -*- coding: utf-8 -*-
"""Защита кода: карточка с дефектом читаемости не уходит в публикацию.

Смысл Фазы 4. Детектор кодов (`corpus_render_codes`) сам ничего не
скрывает — он пишет список id, а флаг ставит `quality_gate`. Здесь
проверяется, что список действительно доезжает до шлюза, и что
поднятый флаг закрывает ВСЕ пути показа, а не только карточку задачи:
каталог, случайную задачу, «похожие», экспорт подборки.

Проверять каждый путь отдельно приходится потому, что фильтр
`needs_quality_review=False` написан в двенадцати местах руками, и
достаточно одного забытого, чтобы дефектная задача уехала ученику.
"""
import os
import tempfile

from django.test import TestCase
from django.urls import reverse

from problems.corpus_converter import render_codes as rc
from problems.management.commands.corpus_render_codes import Command
from problems.models import Problem


class GateListTests(TestCase):
    """Список id для `quality_gate`: формат и что в него попадает."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def _write(self, details):
        path = Command._write_gate_list(details, self.dir.name)
        with open(path, encoding='utf-8') as fh:
            return [ln for ln in fh.read().splitlines()
                    if ln and not ln.startswith('#')]

    def test_p0_and_p1_are_listed(self):
        rows = self._write({11: ['MISS'], 22: ['COMM']})
        self.assertEqual([r.split('\t')[0] for r in rows], ['11', '22'])
        self.assertEqual(rows[0].split('\t')[1], 'P0')
        self.assertEqual(rows[1].split('\t')[1], 'P1')

    def test_p2_only_is_not_listed(self):
        """Косметика не прячет задачу: TABLE и OVER-M сняты правкой
        шаблона, а не карточкой."""
        self.assertEqual(self._write({33: ['TABLE', 'EMPTY-MATH']}), [])

    def test_worst_priority_wins(self):
        rows = self._write({44: ['TABLE', 'MISS']})
        self.assertEqual(rows[0].split('\t')[1], 'P0')

    def test_file_lands_where_quality_gate_looks(self):
        """Имя файла — договор с `quality_gate`; разъедется молча."""
        Command._write_gate_list({11: ['MISS']}, self.dir.name)
        self.assertTrue(os.path.exists(
            os.path.join(self.dir.name, 'render_codes_ids.txt')))
        source = open(
            os.path.join('problems', 'management', 'commands',
                         'quality_gate.py'), encoding='utf-8').read()
        self.assertIn("'render_codes_ids.txt'", source,
                      'quality_gate перестал читать список кодов читаемости')


class FlaggedProblemIsInvisibleTests(TestCase):
    """Поднятый флаг закрывает все пути показа."""

    def setUp(self):
        self.problem = Problem.objects.create(
            title='Дефектная карточка',
            statement='На рисунке изображён график спроса.',
            status=Problem.Status.PUBLISHED,
            needs_quality_review=True,
            hidden_pending_review=False,
        )
        self.good = Problem.objects.create(
            title='Исправная карточка',
            statement='Найдите равновесную цену на рынке пшеницы.',
            status=Problem.Status.PUBLISHED,
            needs_quality_review=False,
            hidden_pending_review=False,
        )

    def test_detail_page_is_not_reachable(self):
        response = self.client.get(
            reverse('catalog:problem_detail', args=[self.problem.pk]))
        self.assertEqual(response.status_code, 404)

    def test_catalog_list_does_not_show_it(self):
        response = self.client.get(reverse('catalog:problem_list'))
        self.assertEqual(response.status_code, 200)
        # Сверяем то, что список ОТОБРАЛ, а не то, как он это нарисовал:
        # у каталога три режима показа с разной разметкой, и проверка по
        # HTML говорила бы о шаблоне, а не о доступе.
        shown = {card['problem'].pk for card in response.context['cards']}
        self.assertNotIn(self.problem.pk, shown)
        self.assertIn(self.good.pk, shown)

    def test_random_problem_never_lands_on_it(self):
        for _ in range(12):
            response = self.client.get(reverse('catalog:random_problem'))
            self.assertNotIn(str(self.problem.pk),
                             response.get('Location', ''))

    def test_similar_block_does_not_show_it(self):
        self.good.similar_problems.add(self.problem)
        response = self.client.get(
            reverse('catalog:problem_detail', args=[self.good.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Дефектная карточка',
                         response.content.decode('utf-8'))

    def test_becomes_visible_only_when_flag_is_cleared(self):
        """Флаг снимается человеком — и только тогда задача появляется."""
        Problem.objects.filter(pk=self.problem.pk).update(
            needs_quality_review=False)
        response = self.client.get(
            reverse('catalog:problem_detail', args=[self.problem.pk]))
        self.assertEqual(response.status_code, 200)


class DetectorFindsTheFixtureTests(TestCase):
    """Та самая карточка и правда считается дефектной детектором."""

    def test_reference_without_figure_is_p0(self):
        blocks = [('Условие', '', 'На рисунке изображён график спроса.')]
        htmls = ['<p>На рисунке изображён график спроса.</p>']
        found = rc.analyze_problem(blocks, htmls)
        self.assertIn('MISS', found)
        self.assertEqual(rc.PRIORITY['MISS'], 'P0')
