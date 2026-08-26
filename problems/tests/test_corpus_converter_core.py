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


class StripJunkCommandsTests(SimpleTestCase):
    def test_removes_medskip_and_friends_without_trace(self):
        from problems.corpus_converter.core import strip_junk_commands
        text = 'Первая часть.\\medskip\n\\noindent Вторая часть.\\quad\\qquad'
        result = strip_junk_commands(text)
        self.assertNotIn('\\medskip', result)
        self.assertNotIn('\\noindent', result)
        self.assertNotIn('\\quad', result)
        self.assertIn('Первая часть.', result)
        self.assertIn('Вторая часть.', result)


class StripColorTests(SimpleTestCase):
    def test_textcolor_keeps_content_drops_color(self):
        from problems.corpus_converter.core import strip_color
        text = 'Ответ: \\textcolor{red}{неверно}.'
        self.assertEqual(strip_color(text), 'Ответ: неверно.')

    def test_bare_color_switch_removed(self):
        from problems.corpus_converter.core import strip_color
        text = '\\color{blue}Текст синим.'
        self.assertEqual(strip_color(text), 'Текст синим.')


class StripTexCommentsTests(SimpleTestCase):
    def test_removes_comment_line_start(self):
        from problems.corpus_converter.core import strip_tex_comments
        text = 'Условие.\n% Q = 2KL (KL=16)\nОтвет: 5.'
        result = strip_tex_comments(text)
        self.assertNotIn('Q = 2KL', result)
        self.assertIn('Условие.', result)
        self.assertIn('Ответ: 5.', result)

    def test_keeps_escaped_percent(self):
        from problems.corpus_converter.core import strip_tex_comments
        text = 'Ставка 20\\% годовых.'
        self.assertEqual(strip_tex_comments(text), text)

    def test_keeps_percent_in_prose(self):
        from problems.corpus_converter.core import strip_tex_comments
        text = 'Курс вырос на 20% за год.'
        self.assertEqual(strip_tex_comments(text), text)


class ConvertEmphasisTests(SimpleTestCase):
    def test_textbf_to_markdown_bold(self):
        from problems.corpus_converter.core import convert_emphasis
        self.assertEqual(convert_emphasis('\\textbf{Важно}'), '**Важно**')

    def test_textit_and_emph_to_markdown_italic(self):
        from problems.corpus_converter.core import convert_emphasis
        self.assertEqual(convert_emphasis('\\textit{тонко}'), '*тонко*')
        self.assertEqual(convert_emphasis('\\emph{тонко}'), '*тонко*')

    def test_existing_markdown_bold_untouched(self):
        from problems.corpus_converter.core import convert_emphasis
        self.assertEqual(convert_emphasis('**уже жирный**'), '**уже жирный**')

    def test_does_not_touch_star_inside_math(self):
        from problems.corpus_converter.core import convert_emphasis
        text, protected = protect_math('Оптимум $Q^*=20$, цена $P^*=5$.')
        result = restore_math(convert_emphasis(text), protected)
        self.assertEqual(result, 'Оптимум $Q^*=20$, цена $P^*=5$.')
