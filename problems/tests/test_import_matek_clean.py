# -*- coding: utf-8 -*-
"""`clean_latex` импортёра МатЭк не смеет чистить ВНУТРИ формул.

Откуда взялось. Сверка #29026 с оригинальным .tex показала, что автор написал
`$y = 57 - 2\\sqrt{x} + 0{,}5x \\quad x \\leqslant 16$`, а в базе лежит то же
самое без `\\quad`. Вырезал его импортёр: одна регулярка чистила `\\quad`,
`\\qquad` и `\\\\` по всему тексту подряд. Вне формулы это верно — там они
служебный мусор. Внутри формулы `\\quad` рисует зазор, и без него функция
слипается с областью определения: «0,5xx ⩽ 16».

Тест сторожит обе стороны: внутри математики чистка молчит, вне — работает
как работала.
"""
from django.test import SimpleTestCase

from problems.management.commands.import_matek import clean_latex


class CleanLatexKeepsMathTests(SimpleTestCase):
    """Содержимое формул проходит через чистку дословно."""

    def test_quad_inside_math_survives(self):
        """Контрольная строка из #29026, названная владельцем поимённо."""
        src = r'$y = 57 - 2\sqrt{x} + 0{,}5x \quad x \leqslant 16$'
        self.assertEqual(clean_latex(src), src)

    def test_quad_inside_math_survives_with_text_around(self):
        src = (r'Найдите наибольшее значение:' '\n'
               r'$y = 1547 + 19x - x^2 \quad x \in [0; 10]$')
        out = clean_latex(src)
        self.assertIn(r'x^2 \quad x \in [0; 10]', out)

    def test_qquad_inside_display_math_survives(self):
        src = r'$$P \qquad Q$$'
        self.assertEqual(clean_latex(src), src)

    def test_row_separator_inside_cases_survives(self):
        r"""`\\` внутри cases разделяет строки. Превращать его в перенос
        строки значит разломать матрицу."""
        src = r'$Y = \begin{cases} 500\sqrt{P} & P \le 100 \\ 5000 & P > 100 \end{cases}$'
        self.assertEqual(clean_latex(src), src)

    def test_bracket_math_survives(self):
        src = r'\[ a \quad b \]'
        self.assertEqual(clean_latex(src), src)


class CleanLatexStillCleansOutsideMathTests(SimpleTestCase):
    """Прежнее поведение вне формул не изменилось."""

    def test_quad_outside_math_still_stripped(self):
        self.assertEqual(clean_latex(r'Слово \quad другое'), 'Слово другое')

    def test_double_backslash_outside_math_becomes_newline(self):
        # Пробел перед переносом остаётся — так было и до правки, сверено
        # с версией функции из предыдущего коммита.
        self.assertEqual(clean_latex(r'Первая \\ вторая'), 'Первая \n вторая')

    def test_textbf_unwrapped(self):
        self.assertEqual(clean_latex(r'\textbf{Жирный} текст'), 'Жирный текст')

    def test_includegraphics_dropped(self):
        self.assertEqual(clean_latex(r'До \includegraphics[width=5cm]{a.png} после'),
                         'До после')

    def test_matek_newline_macro_becomes_break(self):
        self.assertEqual(clean_latex(r'\n первый \n второй'), 'первый \n второй')

    def test_mixed_text_and_math(self):
        """Вне формулы чистим, внутри — нет, в одной строке."""
        src = r'Дано \quad $a \quad b$ и \textbf{всё}'
        self.assertEqual(clean_latex(src), r'Дано $a \quad b$ и всё')
