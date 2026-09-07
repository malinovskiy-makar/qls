# -*- coding: utf-8 -*-
r"""Детекторы 19 кодов читаемости из аудита 3 000 карточек.

Каждый тест построен на живом фрагменте из реестра аудита, а не на
выдуманном примере: детектор обязан ловить то, что человек уже назвал
дефектом, и не ловить то, что тот же человек счёл нормой.

Отдельно закреплены два случая, где первая версия ошибалась на живых
данных, — они и есть настоящая проверка:
* `$$` в начале выключной формулы принималось за пустую формулу
  (46 исправных задач получали код ни за что);
* `INCOMP` считался по всей карточке, и задача с пустым условием, но
  длинным разбором, выглядела полноценной (#5003).
"""
from django.test import SimpleTestCase

from problems.corpus_converter import render_codes as rc

BS = chr(92)


def block(text, name='Условие'):
    """Блок «как на показе»: текст и его HTML."""
    return [(name, '', text)], ['<p>%s</p>' % text]


def codes(text, name='Условие', html=None, **kw):
    blocks, htmls = block(text, name)
    if html is not None:
        htmls = [html]
    return rc.analyze_problem(blocks, htmls, **kw)


LONG = ('Фирма работает на конкурентном рынке и выбирает выпуск так, '
        'чтобы максимизировать прибыль при заданных издержках. ')


class VisibleTextTests(SimpleTestCase):
    """Служебные символы ищутся ВНЕ формул: внутри они законны."""

    def test_math_is_cut_out(self):
        seen = rc.visible_text('<p>цена $' + BS + 'frac{a}{b}$ растёт</p>')
        self.assertNotIn(BS, seen)
        self.assertIn('растёт', seen)

    def test_display_math_is_cut_out(self):
        seen = rc.visible_text('<p>вот $$x' + BS + 'cdot y$$ конец</p>')
        self.assertNotIn('cdot', seen)
        self.assertIn('конец', seen)

    def test_escaped_dollar_is_money_not_math(self):
        seen = rc.visible_text('<p>цена ' + BS + '$3 и ' + BS + '$12</p>')
        self.assertIn('$3', seen)
        self.assertIn('$12', seen)


class EmptyMathTests(SimpleTestCase):
    def test_display_opener_is_not_empty_math(self):
        """Живая ошибка: `$$` формулы принималось за пустую формулу."""
        self.assertEqual(
            rc.empty_math_spans('равны:\n\n$$S+0.02S+' + BS + 'frac{1}{2}$$'),
            [])

    def test_truly_empty_is_found(self):
        self.assertTrue(rc.empty_math_spans('текст $$$$ дальше'))
        self.assertTrue(rc.empty_math_spans('текст $  $ дальше'))

    def test_two_inline_formulas_in_a_row(self):
        self.assertEqual(rc.empty_math_spans('было $a$ и $b$ стало'), [])

    def test_display_formula_gets_no_code_through_the_gate(self):
        """Через ВЕСЬ детектор, а не только через вспомогательную функцию.

        Проверять только `empty_math_spans` мало: ошибка жила в месте
        вызова, и тест на функцию оставался бы зелёным при откате."""
        text = (LONG + 'равны:\n\n$$S+0.02S+' + BS + 'frac{15}{16}S$$')
        self.assertNotIn('EMPTY-MATH', codes(text))

    def test_empty_formula_gets_the_code_through_the_gate(self):
        self.assertIn('EMPTY-MATH', codes(LONG + ' вот $$$$ и всё'))


class IncompTests(SimpleTestCase):
    def test_empty_statement_with_long_solution(self):
        """#5003: условия нет, разбор длинный — карточка всё равно пустая."""
        blocks = [('Условие', '', ''), ('Решение', '', LONG * 2)]
        htmls = ['', '<p>%s</p>' % (LONG * 2)]
        self.assertIn('INCOMP', rc.analyze_problem(blocks, htmls))

    def test_editor_note_is_not_a_problem(self):
        """#3986: «А вот так добавить картинку» — заметка автора."""
        self.assertIn('INCOMP', codes('А вот так добавить картинку'))

    def test_form_header_is_not_a_problem(self):
        """#5053: шапка бланка."""
        self.assertIn('INCOMP',
                      codes('Выберите единственный верный ответ:'))

    def test_real_problem_is_not_incomp(self):
        self.assertNotIn('INCOMP', codes(LONG))

    def test_short_stem_with_parts_is_not_incomp(self):
        """Короткое условие плюс подпункты — нормальная задача."""
        blocks = [('Условие', '', 'Выберите верные утверждения о МВФ.'),
                  ('Часть а', '', LONG)]
        htmls = ['<p>x</p>', '<p>%s</p>' % LONG]
        self.assertNotIn('INCOMP', rc.analyze_problem(blocks, htmls))


class ServiceSyntaxTests(SimpleTestCase):
    def test_comment_is_found(self):
        self.assertIn('COMM', codes(LONG + '%нижняя огибающая'))

    def test_percent_after_number_is_not_a_comment(self):
        self.assertNotIn('COMM', codes(LONG + 'налог 20 % от выручки'))
        self.assertNotIn('COMM', codes(LONG + 'ставка 25% от выручки'))

    def test_float_options_are_found(self):
        """`[htpb]` без слеша: 296 живых задач у новых источников."""
        self.assertIn('BOX', codes(LONG + '[htpb] дальше текст'))

    def test_tabular_spec_is_found(self):
        self.assertIn('RTAB', codes(LONG + 'p{9cm} и дальше'))

    def test_ampersand_is_found(self):
        self.assertIn('RTAB', codes(LONG + 'H (Умный) 300 & 200 & 60%'))

    def test_backslash_is_found(self):
        self.assertIn('SLASH', codes(LONG + 'строка ' + BS + BS + ' конец'))

    def test_braces_are_found(self):
        self.assertIn('BRACE', codes(LONG + '{МЭ Москва (2021)}'))

    def test_ascii_math_is_found(self):
        self.assertIn('RAW-MATH', codes(LONG + 'sqrt(2) и x^2'))
        self.assertIn('RAW-MATH', codes(LONG + 'налоги => результат'))

    def test_markdown_stars_are_found(self):
        self.assertIn('MD', codes('***** Диплом Шиварова ' + LONG))

    def test_clean_text_has_no_codes(self):
        self.assertEqual(codes(LONG), {})


class CollapsedEnvironmentTests(SimpleTestCase):
    def test_cases_without_row_separator(self):
        text = (LONG + '$$' + BS + 'begin{cases}\nx > 0\ny < 5\n'
                + BS + 'end{cases}$$')
        self.assertIn('COLL', codes(text))

    def test_cases_with_separator_is_fine(self):
        text = (LONG + '$$' + BS + 'begin{cases}\nx > 0 ' + BS + BS
                + '\ny < 5\n' + BS + 'end{cases}$$')
        self.assertNotIn('COLL', codes(text))


class LinkTests(SimpleTestCase):
    def test_tyk_placeholder(self):
        self.assertIn('LINK', codes(LONG + 'условие тык здесь'))

    def test_real_anchor_is_fine(self):
        html = '<p>%s <a href="https://x.ru">тык</a></p>' % LONG
        self.assertNotIn('LINK', codes(LONG + ' тык', html=html))


class SolutionLeakTests(SimpleTestCase):
    def test_solution_inside_statement(self):
        self.assertIn('SOL', codes(LONG + ' РЕШЕНИЕ Пусть взяли сумму S.'))

    def test_solution_block_itself_is_fine(self):
        self.assertNotIn(
            'SOL', codes(LONG + ' РЕШЕНИЕ Пусть S.', name='Решение'))


class FigureTests(SimpleTestCase):
    def test_reference_without_object(self):
        self.assertIn('MISS', codes('На рисунке изображён график спроса. '
                                    + LONG))

    def test_reference_with_image_is_fine(self):
        text = 'На рисунке изображён график спроса. ' + LONG
        html = '<p>%s</p><img src="/catalog/figure/1.svg">' % text
        self.assertNotIn('MISS', codes(text, html=html))

    def test_reference_with_table_is_fine(self):
        text = 'Таблица приведена ниже. ' + LONG
        html = '<p>%s</p><table><tr><td>1</td></tr></table>' % text
        self.assertNotIn('MISS', codes(text, html=html))


class TableTests(SimpleTestCase):
    def test_ragged_table_is_broken(self):
        html = ('<table><tr><td>1</td><td>2</td></tr>'
                '<tr><td>3</td></tr></table>')
        self.assertIn('BAD-TABLE', codes(LONG, html=html))

    def test_even_table_is_only_cosmetic(self):
        html = ('<p>%s</p><table><tr><td>1</td><td>2</td></tr>'
                '<tr><td>3</td><td>4</td></tr></table>' % LONG)
        got = codes(LONG, html=html)
        self.assertNotIn('BAD-TABLE', got)
        self.assertIn('TABLE', got)

    def test_pipe_leaked_as_text(self):
        """#4374: разметка `| a | b |` частью осталась абзацем."""
        html = '<p>%s</p><p>|</p><table><tr><td>1</td></tr></table>' % LONG
        self.assertIn('BAD-TABLE', codes(LONG, html=html))


class SvgTests(SimpleTestCase):
    """Повторы id ищутся ВНУТРИ одной картинки.

    Боевой показ отдаёт SVG как `<img src="/catalog/figure/N.svg">` —
    отдельным документом, и столкнуться идентификаторами двух разных
    картинок там негде. Это был дефект инструмента предпросмотра,
    который вклеивал все SVG в одну страницу."""

    def test_duplicate_ids_inside_one_figure(self):
        svg = ('<svg><clipPath id="clip1"/><clipPath id="clip1"/>'
               '<g id="page1"/></svg>')
        self.assertIn('SVG', codes(LONG, figure_svgs=[svg]))

    def test_unique_ids_are_fine(self):
        svg = '<svg><clipPath id="c1"/><clipPath id="c2"/></svg>'
        self.assertNotIn('SVG', codes(LONG, figure_svgs=[svg]))


class WidthCodeTests(SimpleTestCase):
    """Пороги аудита: 800 px — переполнение, 600 px — узкий экран."""

    def test_over(self):
        from problems.corpus_converter.width_probe import codes_for_widths
        self.assertEqual([c for c, _d in codes_for_widths([120.0, 2644.1])],
                         ['OVER'])

    def test_over_mobile(self):
        from problems.corpus_converter.width_probe import codes_for_widths
        self.assertEqual([c for c, _d in codes_for_widths([725.0])],
                         ['OVER-M'])

    def test_narrow_formula_is_fine(self):
        from problems.corpus_converter.width_probe import codes_for_widths
        self.assertEqual(codes_for_widths([120.0, 300.0]), [])


class PriorityTests(SimpleTestCase):
    def test_every_code_has_priority_and_meaning(self):
        self.assertEqual(set(rc.PRIORITY), set(rc.MEANING))
        self.assertEqual(len(rc.PRIORITY), 19,
                         'реестр аудита — ровно 19 кодов')
