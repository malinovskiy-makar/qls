# -*- coding: utf-8 -*-
"""Фаза 2 сессии 2026-08-27: инвариант сохранности содержимого.

Живые фикстуры — ровно те карточки, на которых аудит зафиксировал
пустые блоки: #41924 (потеря), #3989 (пустой апстрим), #30530 (условие
из одного TeX-комментария), #4053 (пустое условие при полных подпунктах).
"""
from django.test import SimpleTestCase

from problems.corpus_converter.structure_guard import (
    CODE_LOST, CODE_NO_SOURCE, check_problem, classify_block, visible_text,
)
from problems.rendering import render_markdown


class VisibleTextTests(SimpleTestCase):
    def test_tags_stripped_and_entities_unescaped(self):
        self.assertEqual(visible_text('<p>a &amp; b</p>'), 'a & b')

    def test_empty_list_item_has_no_visible_text(self):
        # Механизм потери #41924, замеренный в Фазе -1.
        self.assertEqual(visible_text('<ol>\n<li></li>\n</ol>\n'), '')


class LostContentTests(SimpleTestCase):
    """#41924: `3.` съедается markdown как номер пустого пункта списка."""

    def test_41924_part_g_is_detected_as_lost(self):
        self.assertEqual(render_markdown('3.'), '<ol>\n<li></li>\n</ol>\n')
        self.assertEqual(classify_block('3.', '3.'), CODE_LOST)

    def test_41924_siblings_are_not_lost(self):
        # У соседних подпунктов `0;`, `1;`, `2;` точки нет — они целы.
        for src in ('0;', '1;', '2;'):
            self.assertIsNone(classify_block(src, src), f'ложная потеря на {src!r}')

    def test_any_numeric_marker_alone_is_lost(self):
        for src in ('1.', '5.', '42.'):
            self.assertEqual(classify_block(src, src), CODE_LOST)

    def test_normal_text_survives(self):
        self.assertIsNone(classify_block('обычное условие', 'обычное условие'))


class EmptySourceTests(SimpleTestCase):
    """Пустой исходник — дефект материала, а НЕ потеря конвертера."""

    def test_3989_empty_subpoints_are_not_reported_as_loss(self):
        self.assertEqual(classify_block('', ''), CODE_NO_SOURCE)

    def test_30530_comment_only_source_is_not_a_loss(self):
        # Живой #30530: условие целиком — `%прошлый интенсив …`.
        src = '%прошлый интенсив - a,b,c (но тут дрегие числа!), d - МЭ МСК 11 класс'
        self.assertEqual(classify_block(src, ''), CODE_NO_SOURCE)

    def test_3989_whole_problem_needs_content(self):
        # Все четыре подпункта пусты в исходнике — задача не решаема.
        blocks = [('Условие', '', ''),
                  ('Часть а', '', ''), ('Часть б', '', ''),
                  ('Часть в', '', ''), ('Часть г', '', '')]
        lost, needs_content = check_problem(blocks)
        self.assertEqual(lost, [])
        self.assertTrue(needs_content)

    def test_4053_empty_statement_with_full_parts_is_still_a_task(self):
        # Живой #4053: условие пустое, подпункты полные — блокировать
        # такую задачу нельзя, содержимое у неё есть.
        blocks = [('Условие', '', ''),
                  ('Часть а', '$TC(Q)=10Q$', '$TC(Q)=10Q$'),
                  ('Часть б', 'парабола ветвями вниз', 'парабола ветвями вниз')]
        lost, needs_content = check_problem(blocks)
        self.assertEqual(lost, [])
        self.assertFalse(needs_content)


class ProblemLevelTests(SimpleTestCase):
    def test_41924_shape_reports_exactly_the_lost_part(self):
        blocks = [('Условие', 'Государство вводит налог', 'Государство вводит налог'),
                  ('Часть а', '0;', '0;'), ('Часть б', '1;', '1;'),
                  ('Часть в', '2;', '2;'), ('Часть г', '3.', '3.')]
        lost, needs_content = check_problem(blocks)
        self.assertEqual(lost, ['Часть г'])
        self.assertFalse(needs_content)

    def test_clean_problem_reports_nothing(self):
        blocks = [('Условие', 'условие задачи', 'условие задачи'),
                  ('Часть а', 'первый пункт', 'первый пункт')]
        self.assertEqual(check_problem(blocks), ([], False))
