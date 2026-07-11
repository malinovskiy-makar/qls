# -*- coding: utf-8 -*-
"""Регресс-тесты чистки LaTeX-мусора (problems.management.commands.fix_latex_junk).

clean_text — чистая функция без обращений к базе, поэтому SimpleTestCase
(без создания тестовой БД). Тесты фиксируют поведение, установленное сессией
«корректировка fix_latex_junk по итогам ревью»:
  - footnote выключен по умолчанию;
  - %-комментарий вырезается до \\n целиком, а не по первому слову; без \\n —
    задача не трогается и уходит на ручной разбор;
  - без единого сработавшего паттерна текст не меняется ни на символ.
"""
from django.test import SimpleTestCase

from problems.management.commands.fix_latex_junk import clean_text


class JunkCommentTests(SimpleTestCase):
    def test_multiword_comment_with_newline_removed_entirely(self):
        # Реальный случай #4853 — раньше вырезалось только первое слово
        # («%благосостояние»), оставляя огрызок «при вмешательстве».
        text = (
            'Осторожно, двери закрываются. %благосостояние при вмешательстве\n'
            '\nПомогите Минтрансу оценить эффективность.'
        )
        cleaned, applied, needs_manual = clean_text(text)
        self.assertEqual(
            cleaned,
            'Осторожно, двери закрываются.\n\nПомогите Минтрансу оценить эффективность.',
        )
        self.assertIn('junk_comment', applied)
        self.assertFalse(needs_manual)
        self.assertNotIn('при вмешательстве', cleaned)

    def test_comment_without_newline_is_skipped_and_flagged_for_manual_review(self):
        text = 'Слипшийся комментарий %этонужноубрать в самом конце текста без переноса'
        cleaned, applied, needs_manual = clean_text(text)
        self.assertEqual(cleaned, text)  # текст НЕ тронут этим паттерном
        self.assertNotIn('junk_comment', applied)
        self.assertTrue(needs_manual)

    def test_percent_inside_dollar_formula_not_touched(self):
        text = 'Пусть $a%b$ — гипотетическая формула без экранирования.'
        cleaned, applied, needs_manual = clean_text(text)
        self.assertEqual(cleaned, text)
        self.assertNotIn('junk_comment', applied)
        self.assertFalse(needs_manual)

    def test_escaped_percent_not_touched(self):
        text = 'Цена $P = 100\\%X$ задаёт кривую спроса.'
        cleaned, applied, needs_manual = clean_text(text)
        self.assertEqual(cleaned, text)
        self.assertNotIn('junk_comment', applied)

    def test_ordinary_percentage_in_text_not_touched(self):
        text = 'ВВП вырос на 20% в этом году по сравнению с прошлым.'
        cleaned, applied, needs_manual = clean_text(text)
        self.assertEqual(cleaned, text)
        self.assertNotIn('junk_comment', applied)
        self.assertFalse(needs_manual)


class PseudoQuotesTests(SimpleTestCase):
    def test_double_angle_quotes_outside_formula_replaced(self):
        text = 'Компания <<Ромашка>> работает на рынке.'
        cleaned, applied, _ = clean_text(text)
        self.assertEqual(cleaned, 'Компания «Ромашка» работает на рынке.')
        self.assertIn('pseudo_quotes', applied)

    def test_double_angle_quotes_inside_formula_not_touched(self):
        text = 'Неравенство $a << b$ означает «много меньше».'
        cleaned, applied, _ = clean_text(text)
        self.assertEqual(cleaned, text)
        self.assertNotIn('pseudo_quotes', applied)


class NoPatternTests(SimpleTestCase):
    def test_text_without_any_pattern_returned_byte_for_byte(self):
        text = 'Обычное условие задачи про спрос и предложение. Цена $P=10$.'
        cleaned, applied, needs_manual = clean_text(text)
        self.assertEqual(cleaned, text)  # байт-в-байт то же содержимое
        self.assertEqual(applied, [])
        self.assertFalse(needs_manual)


class FootnoteTests(SimpleTestCase):
    def test_footnote_not_touched_when_flag_disabled_by_default(self):
        text = 'Вопрос \\footnote{важная подсказка к решению} про экономику.'
        cleaned, applied, _ = clean_text(text)
        self.assertEqual(cleaned, text)
        self.assertNotIn('footnote', applied)

    def test_footnote_removed_when_include_footnote_true(self):
        text = 'Вопрос \\footnote{важная подсказка к решению} про экономику.'
        cleaned, applied, _ = clean_text(text, include_footnote=True)
        self.assertEqual(cleaned, 'Вопрос про экономику.')
        self.assertIn('footnote', applied)
