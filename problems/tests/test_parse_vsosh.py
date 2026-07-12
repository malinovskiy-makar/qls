# -*- coding: utf-8 -*-
"""
Тесты parse_vsosh_region: косметика текста (слэш-дроби -> \\frac только
внутри математики, двойные дефисы/тире -> «—» только вне математики),
числовой ответ (correct) остаётся нетронутым.
"""
from django.test import SimpleTestCase

from problems.management.commands.parse_vsosh_region import (
    canonicalize_answer, postprocess_text,
)


class PostprocessTextTests(SimpleTestCase):

    def test_slash_fraction_in_math_becomes_frac(self):
        self.assertEqual(
            postprocess_text('Уравнение $Y= 2M/P$, где $Y$ реальный ВВП.'),
            'Уравнение $Y= \\frac{2M}{P}$, где $Y$ реальный ВВП.')

    def test_double_dash_in_text_becomes_emdash(self):
        self.assertEqual(
            postprocess_text('$Y$ –– реальный ВВП, $M$ –– денежная масса'),
            '$Y$ — реальный ВВП, $M$ — денежная масса')

    def test_ascii_double_hyphen_becomes_emdash(self):
        self.assertEqual(postprocess_text('текст --  продолжение'),
                         'текст —  продолжение')

    def test_dash_inside_math_not_touched(self):
        # внутри математики дефис может быть минусом — не трогаем
        text = postprocess_text('$Q^{*}= 40 -- 2$ пример')
        self.assertIn('40 -- 2', text)

    def test_slash_outside_math_not_touched(self):
        self.assertEqual(postprocess_text('расстояние 60 км/ч по трассе'),
                         'расстояние 60 км/ч по трассе')

    def test_complex_subscript_fraction_not_touched(self):
        # P_{e}/40 — не «простая» дробь (числитель с индексом), не трогаем
        text = postprocess_text('$100/80 \\le P_{e}/40$')
        self.assertEqual(text, '$\\frac{100}{80} \\le P_{e}/40$')

    def test_existing_frac_not_double_converted(self):
        text = postprocess_text('$80 = \\frac{100}{1+r_{12}}$')
        self.assertEqual(text, '$80 = \\frac{100}{1+r_{12}}$')


class CanonicalizeAnswerUntouchedTests(SimpleTestCase):

    def test_fraction_answer_stays_exact(self):
        # correct у числовых вопросов не проходит через postprocess_text —
        # его парсит parse_exact_number, дробь должна остаться как есть
        (value, unit), err = canonicalize_answer('1/3.')
        self.assertIsNone(err)
        self.assertEqual(value, '1/3')
        self.assertEqual(unit, '')
