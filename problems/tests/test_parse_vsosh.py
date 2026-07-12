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

    def test_existing_frac_not_double_converted(self):
        text = postprocess_text('$80 = \\frac{100}{1+r_{12}}$')
        self.assertEqual(text, '$80 = \\frac{100}{1+r_{12}}$')

    def test_complex_expression_fraction_not_touched(self):
        # 10/(5 \cdot 2) и (8w-w^2+20)/(10-w) — составные, не «атомы», не трогаем
        self.assertEqual(postprocess_text('$10/(5 \\cdot 2)$'),
                         '$10/(5 \\cdot 2)$')
        text = postprocess_text('$(8w-w^{2} + 20)/(10 -w) = w+ 2$')
        self.assertEqual(text, '$(8w-w^{2} + 20)/(10 -w) = w+ 2$')

    def test_subscript_numerator_becomes_frac(self):
        # P_e/40 — атом с индексом (без скобок в исходнике) -> \frac
        self.assertEqual(postprocess_text('$P_e/40$'), '$\\frac{P_e}{40}$')

    def test_braced_subscript_numerator_becomes_frac(self):
        # P_{e}/40 — та же переменная, но как реально рендерит парсер (с {})
        text = postprocess_text('$100/80 \\le P_{e}/40$')
        self.assertEqual(text, '$\\frac{100}{80} \\le \\frac{P_{e}}{40}$')

    def test_superscript_numerator_becomes_frac(self):
        # Q^2/2 -> \frac{Q^2}{2}
        self.assertEqual(postprocess_text('$Q^2/2$'), '$\\frac{Q^2}{2}$')

    def test_plain_slash_fraction_in_expression(self):
        self.assertEqual(postprocess_text('$11 - Q/2$'), '$11 - \\frac{Q}{2}$')

    def test_paren_fraction_with_power_gets_left_right(self):
        # (Q/2)^7 -> \left(\frac{Q}{2}\right)^{7} — скобки растут вместе с дробью
        self.assertEqual(postprocess_text('$(Q/2)^7$'),
                         '$\\left(\\frac{Q}{2}\\right)^{7}$')

    def test_paren_fraction_with_braced_power_gets_left_right(self):
        text = postprocess_text('$3(Q/2)^{7} + 7(Q/2)^{3}$')
        self.assertEqual(
            text,
            '$3\\left(\\frac{Q}{2}\\right)^{7} + 7\\left(\\frac{Q}{2}\\right)^{3}$')

    def test_paren_fraction_without_power_stays_plain_parens(self):
        # без внешней степени скобки не поднимаем — обычных достаточно
        text = postprocess_text('$TC_{1}(Q/2)+TC_{2}(Q/2)$')
        self.assertEqual(text, '$TC_{1}(\\frac{Q}{2})+TC_{2}(\\frac{Q}{2})$')

    def test_sqrt_letter_run_gets_braces(self):
        # √KL из юникод-математики: винкулум в PDF накрывает весь ран
        self.assertEqual(postprocess_text('$Q=\\sqrt KL$'),
                         '$Q=\\sqrt{KL}$')
        self.assertEqual(postprocess_text('$10 \\sqrt Q  \\cdot Q$'),
                         '$10 \\sqrt{Q}  \\cdot Q$')

    def test_root_index_before_sqrt(self):
        # маленькая «4» перед радикалом — корень 4-й степени, не множитель
        self.assertEqual(postprocess_text('$Q= ^{4}\\sqrt KL$'),
                         '$Q= \\sqrt[4]{KL}$')

    def test_braced_sqrt_not_double_wrapped(self):
        self.assertEqual(postprocess_text('$\\sqrt{KL}+1$'), '$\\sqrt{KL}+1$')


class CanonicalizeAnswerUntouchedTests(SimpleTestCase):

    def test_fraction_answer_stays_exact(self):
        # correct у числовых вопросов не проходит через postprocess_text —
        # его парсит parse_exact_number, дробь должна остаться как есть
        (value, unit), err = canonicalize_answer('1/3.')
        self.assertIsNone(err)
        self.assertEqual(value, '1/3')
        self.assertEqual(unit, '')
