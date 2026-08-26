from django.test import SimpleTestCase

from problems.corpus_converter.core import wrap_bare_environments, protect_math, restore_math


class WrapBareEnvironmentsTests(SimpleTestCase):
    def test_wraps_bare_equation(self):
        text = 'Найдите Q.\n\\begin{equation}\nQ = 10 - P\n\\end{equation}\nОтвет готов.'
        result = wrap_bare_environments(text)
        self.assertIn('$$\n\\begin{equation}\nQ = 10 - P\n\\end{equation}\n$$', result)

    def test_does_not_double_wrap_already_wrapped(self):
        text = 'Формула: $$\\begin{align}Q = 10 - P\\end{align}$$'
        result = wrap_bare_environments(text)
        self.assertEqual(text, result)

    def test_does_not_touch_cases_environment(self):
        text = 'Кусочная функция $$f(x) = \\begin{cases}1 & x>0\\\\0 & x\\le 0\\end{cases}$$'
        result = wrap_bare_environments(text)
        self.assertEqual(text, result)


class ProtectMathTests(SimpleTestCase):
    def test_protects_and_restores_dollar_math(self):
        text = 'Цена $P^*=10$ и объём $Q^*=5$.'
        protected_text, spans = protect_math(text)
        self.assertNotIn('P^*', protected_text)
        self.assertEqual(restore_math(protected_text, spans), text)

    def test_protects_array_inside_double_dollar(self):
        text = 'Матрица: $$\\begin{array}{cc}1&2\\\\3&4\\end{array}$$ конец.'
        protected_text, spans = protect_math(text)
        self.assertNotIn('array', protected_text)
        self.assertEqual(restore_math(protected_text, spans), text)
