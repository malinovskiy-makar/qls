from django.test import SimpleTestCase

from problems.corpus_converter.core import (
    wrap_bare_environments, protect_math, restore_math,
    normalize_dashes, normalize_quotes, find_images,
)


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


class ConvertListsTests(SimpleTestCase):
    def test_itemize_to_markdown_bullets(self):
        from problems.corpus_converter.core import convert_lists
        text = '\\begin{itemize}\\item Первое\\item Второе\\end{itemize}'
        result = convert_lists(text)
        self.assertEqual(result, '- Первое\n- Второе')

    def test_enumerate_to_markdown_numbers(self):
        from problems.corpus_converter.core import convert_lists
        text = '\\begin{enumerate}\\item Первое\\item Второе\\end{enumerate}'
        result = convert_lists(text)
        self.assertEqual(result, '1. Первое\n2. Второе')

    def test_bare_dash_at_line_start_not_touched(self):
        from problems.corpus_converter.core import convert_lists
        # Ловушка sweep-диагностики: '-' в начале строки — часто обрыв
        # формулы на переносе, не буллит. Конвертер его не трогает.
        text = 'Баланс:\n-\nэ (перенос строки внутри формулы PDF-нарезки)'
        self.assertEqual(convert_lists(text), text)

    def test_bare_digit_paren_at_line_start_not_touched(self):
        from problems.corpus_converter.core import convert_lists
        # Ловушка: '2018)' — год исходного вопроса, не номер пункта списка.
        text = '2018) Активами Центрального банка (ЦБ) являются:'
        self.assertEqual(convert_lists(text), text)


class ConvertTablesTests(SimpleTestCase):
    def test_simple_tabular_to_markdown_table(self):
        from problems.corpus_converter.core import convert_tables
        text = (
            '\\begin{tabular}{|l|c|}\\hline\n'
            'Показатель & Значение \\\\\\hline\n'
            'Q & 10 \\\\\\hline\n'
            '\\end{tabular}'
        )
        result, complex_found = convert_tables(text)
        self.assertFalse(complex_found)
        self.assertIn('| Показатель | Значение |', result)
        self.assertIn('| --- | --- |', result)
        self.assertIn('| Q | 10 |', result)
        self.assertNotIn('\\begin{tabular}', result)

    def test_complex_table_left_untouched_and_flagged(self):
        from problems.corpus_converter.core import convert_tables
        text = (
            '\\begin{tabular}{|l|c|c|}\\hline\n'
            '\\multicolumn{2}{|c|}{Итого} & 100 \\\\\\hline\n'
            '\\end{tabular}'
        )
        result, complex_found = convert_tables(text)
        self.assertTrue(complex_found)
        self.assertEqual(result, text)

    def test_multirow_also_flags_complex(self):
        from problems.corpus_converter.core import convert_tables
        text = '\\begin{tabular}{|l|}\\multirow{2}{*}{X}\\end{tabular}'
        _, complex_found = convert_tables(text)
        self.assertTrue(complex_found)

    def test_existing_markdown_table_untouched(self):
        from problems.corpus_converter.core import convert_tables
        text = '| A | B |\n| --- | --- |\n| 1 | 2 |'
        result, complex_found = convert_tables(text)
        self.assertEqual(result, text)
        self.assertFalse(complex_found)

    def test_empty_table_after_hline_strip_flags_complex(self):
        from problems.corpus_converter.core import convert_tables
        text = '\\begin{tabular}{|l|}\\hline\\end{tabular}'
        result, complex_found = convert_tables(text)
        self.assertEqual(result, text)
        self.assertTrue(complex_found)


class FootnoteTests(SimpleTestCase):
    def test_extracts_single_footnote(self):
        from problems.corpus_converter.core import extract_footnotes
        text = 'Цена росла\\footnote{данные ЦБ за 2020 год} весь квартал.'
        result, notes = extract_footnotes(text)
        self.assertEqual(result, 'Цена росла весь квартал.')
        self.assertEqual(notes, ['данные ЦБ за 2020 год'])

    def test_extracts_multiple_footnotes_in_order(self):
        from problems.corpus_converter.core import extract_footnotes
        text = 'Первая\\footnote{сноска раз} и вторая\\footnote{сноска два}.'
        result, notes = extract_footnotes(text)
        self.assertEqual(result, 'Первая и вторая.')
        self.assertEqual(notes, ['сноска раз', 'сноска два'])

    def test_append_single_note(self):
        from problems.corpus_converter.core import append_footnote_notes
        result = append_footnote_notes('Решение готово.', ['данные ЦБ за 2020 год'])
        self.assertEqual(
            result,
            'Решение готово.\n\nПримечание: данные ЦБ за 2020 год',
        )

    def test_append_multiple_notes_numbered(self):
        from problems.corpus_converter.core import append_footnote_notes
        result = append_footnote_notes('Решение готово.', ['раз', 'два'])
        self.assertEqual(
            result,
            'Решение готово.\n\nПримечание 1: раз\nПримечание 2: два',
        )

    def test_append_no_notes_is_noop(self):
        from problems.corpus_converter.core import append_footnote_notes
        self.assertEqual(append_footnote_notes('Решение готово.', []), 'Решение готово.')


class NormalizeDashesTests(SimpleTestCase):
    def test_triple_hyphen_to_em_dash(self):
        self.assertEqual(normalize_dashes('рост---за год'), 'рост—за год')

    def test_double_hyphen_to_en_dash(self):
        self.assertEqual(normalize_dashes('2020--2021'), '2020–2021')

    def test_spaced_single_hyphen_to_em_dash(self):
        self.assertEqual(
            normalize_dashes('Спрос растёт - предложение падает'),
            'Спрос растёт — предложение падает',
        )

    def test_hyphen_inside_word_untouched(self):
        # Составное слово — не тире, трогать нельзя.
        self.assertEqual(normalize_dashes('объект-договор'), 'объект-договор')

    def test_hyphen_in_negative_number_untouched(self):
        self.assertEqual(normalize_dashes('температура -5 градусов'), 'температура -5 градусов')


class NormalizeQuotesTests(SimpleTestCase):
    def test_angle_quotes_to_guillemets(self):
        self.assertEqual(normalize_quotes('<<Ромашка>>'), '«Ромашка»')

    def test_straight_double_quotes_alternate_to_guillemets(self):
        self.assertEqual(
            normalize_quotes('фирма "Ромашка" продала "Одуванчик"'),
            'фирма «Ромашка» продала «Одуванчик»',
        )


class FindImagesTests(SimpleTestCase):
    def test_finds_markdown_image(self):
        text = 'График: ![](https://s3.example/graph.png) выше.'
        images = find_images(text)
        self.assertEqual(images, [
            {'original_ref': 'https://s3.example/graph.png', 'kind': 'markdown'},
        ])

    def test_finds_includegraphics(self):
        text = '\\includegraphics{eq.png} показывает рост.'
        images = find_images(text)
        self.assertEqual(images, [{'original_ref': 'eq.png', 'kind': 'includegraphics'}])

    def test_finds_bare_url_not_already_matched(self):
        text = 'Смотри https://example.com/chart.jpg для деталей.'
        images = find_images(text)
        self.assertEqual(
            images, [{'original_ref': 'https://example.com/chart.jpg', 'kind': 'url'}],
        )

    def test_bare_url_inside_markdown_image_not_double_counted(self):
        text = '![](https://s3.example/graph.png)'
        images = find_images(text)
        self.assertEqual(len(images), 1)

    def test_no_images_returns_empty_list(self):
        self.assertEqual(find_images('Обычный текст без картинок.'), [])
