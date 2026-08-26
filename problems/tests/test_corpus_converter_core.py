from django.test import SimpleTestCase

from problems.corpus_converter.core import (
    wrap_bare_environments, protect_math, restore_math,
    normalize_dashes, normalize_quotes, find_images, convert_text_field,
    convert_problem, strip_control_and_bom_chars, unwrap_math_wrapped_tables,
    reconstruct_orphaned_tabular, strip_multicols_wrapper, strip_hypertarget,
    strip_junk_commands, convert_tables, strip_center_wrapper,
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

    def test_wraps_bare_align_star(self):
        text = 'Вычислим.\n\\begin{align*}\nx = 1\n\\end{align*}\nГотово.'
        result = wrap_bare_environments(text)
        self.assertIn('$$\n\\begin{align*}\nx = 1\n\\end{align*}\n$$', result)

    def test_wraps_bare_equation_star(self):
        text = '\\begin{equation*}\ny = 2x\n\\end{equation*}'
        result = wrap_bare_environments(text)
        self.assertIn('$$\n\\begin{equation*}\ny = 2x\n\\end{equation*}\n$$', result)


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


class ConvertTextFieldTests(SimpleTestCase):
    def test_empty_text_returns_empty_result(self):
        result = convert_text_field('')
        self.assertEqual(result, {
            'text_md': '', 'images': [], 'complex_table': False, 'warnings': [],
        })

    def test_full_pipeline_on_mixed_latex_text(self):
        text = (
            'Фирма \\textbf{"Ромашка"} максимизирует прибыль\\footnote{см. отчёт}.'
            '\\medskip\n'
            'Цена $P^*=10$ упала на 20\\%---сильно.\n'
            '\\begin{itemize}\\item Спрос\\item Предложение\\end{itemize}'
        )
        result = convert_text_field(text)
        self.assertIn('**«Ромашка»**', result['text_md'])
        self.assertIn('$P^*=10$', result['text_md'])
        self.assertIn('20\\%', result['text_md'])
        self.assertIn('—сильно', result['text_md'])
        self.assertIn('- Спрос', result['text_md'])
        self.assertIn('- Предложение', result['text_md'])
        self.assertIn('Примечание: см. отчёт', result['text_md'])
        self.assertNotIn('\\medskip', result['text_md'])
        self.assertNotIn('\\textbf', result['text_md'])
        self.assertFalse(result['complex_table'])

    def test_math_survives_full_pipeline_untouched(self):
        text = 'Оптимум $Q^*=20$ и $P^*=5$, индекс $x_1$ и $x_2$.'
        result = convert_text_field(text)
        self.assertIn('$Q^*=20$', result['text_md'])
        self.assertIn('$P^*=5$', result['text_md'])
        self.assertIn('$x_1$', result['text_md'])
        self.assertIn('$x_2$', result['text_md'])


class RendererRoundTripTests(SimpleTestCase):
    def test_converted_output_renders_without_crashing(self):
        from problems.rendering import render_markdown
        text = (
            '\\textbf{Фирма} максимизирует $\\pi = P \\cdot Q - C(Q)$.\n'
            '\\begin{itemize}\\item Спрос\\item Предложение\\end{itemize}'
        )
        result = convert_text_field(text)
        html = render_markdown(result['text_md'])
        self.assertIn('<strong>Фирма</strong>', html)
        self.assertIn('<li>Спрос</li>', html)
        self.assertIn('$\\pi = P \\cdot Q - C(Q)$', html)


class ConvertProblemTests(SimpleTestCase):
    def test_update_mode_uses_existing_parts_as_is(self):
        # ILE-подобный случай: подпункты уже в базе как ProblemPart, из
        # текста заново их вычленять не нужно и не следует.
        result = convert_problem(
            statement='Общее условие с \\textbf{данными}.',
            existing_parts=[('а', 'Найдите $Q$.'), ('б', 'Найдите $P$.')],
        )
        self.assertEqual(len(result['parts']), 2)
        self.assertEqual(result['parts'][0]['label'], 'а')
        self.assertIn('$Q$', result['parts'][0]['statement_md'])
        self.assertIn('**данными**', result['statement_md'])

    def test_insert_mode_detects_subpoints_from_raw_text(self):
        # Школково-подобный случай: подпункты живут внутри statement_tex
        # текстом, existing_parts не передан вовсе.
        text = 'Дано уравнение спроса.\nа) Найдите $Q$.\nб) Найдите $P$.'
        result = convert_problem(statement=text, existing_parts=None)
        self.assertEqual(len(result['parts']), 2)
        self.assertEqual(result['parts'][0]['label'], 'а')
        self.assertIn('Найдите $Q$', result['parts'][0]['statement_md'])
        self.assertIn('Дано уравнение спроса.', result['statement_md'])

    def test_insert_mode_no_subpoints_found_gives_empty_parts(self):
        result = convert_problem(statement='Обычная задача без пунктов.', existing_parts=None)
        self.assertEqual(result['parts'], [])

    def test_candidate_parts_always_have_answer_key(self):
        # ProblemPart.answer не blank=True — кандидат обязан нести ключ,
        # даже пустой, иначе будущий реальный импорт споткнётся.
        result = convert_problem(
            statement='Условие.\nа) Пункт без ответа в тексте.',
            existing_parts=None,
        )
        self.assertIn('answer', result['parts'][0])

    def test_images_and_complex_table_bubble_up_from_all_fields(self):
        result = convert_problem(
            statement='\\includegraphics{gr.png}',
            answer='',
            solution='\\begin{tabular}{|l|l|}\\multicolumn{2}{|c|}{X}\\end{tabular}',
        )
        self.assertEqual(result['images'], [{'original_ref': 'gr.png', 'kind': 'includegraphics'}])
        self.assertTrue(result['complex_table'])

    def test_answer_and_solution_md_are_returned(self):
        result = convert_problem(
            statement='Условие.',
            answer='\\textbf{Ответ}: 42.',
            solution='Решение с $x^2$.',
        )
        self.assertIn('**Ответ**', result['answer_md'])
        self.assertIn('$x^2$', result['solution_md'])

    def test_answer_and_solution_md_empty_when_not_given(self):
        result = convert_problem(statement='Условие.')
        self.assertEqual(result['answer_md'], '')
        self.assertEqual(result['solution_md'], '')


class StripControlAndBomCharsTests(SimpleTestCase):
    """Scale-up: SolveHub, атлас — U+0002/BOM/U+2028/nbsp/псевдо-HTML."""

    def test_removes_control_char_and_bom(self):
        text = 'пере\u0002меннойХ и \ufeffэтот текст'
        result = strip_control_and_bom_chars(text)
        self.assertNotIn('\u0002', result)
        self.assertNotIn('\ufeff', result)
        self.assertEqual(result, 'переменнойХ и этот текст')

    def test_line_separator_becomes_newline(self):
        text = 'Первая строка\u2028Вторая строка'
        self.assertEqual(strip_control_and_bom_chars(text), 'Первая строка\nВторая строка')

    def test_nbsp_becomes_regular_space(self):
        self.assertEqual(strip_control_and_bom_chars('100\u00a0рублей'), '100 рублей')

    def test_pseudo_html_li_removed(self):
        self.assertEqual(strip_control_and_bom_chars('Пункт<\\li> первый'), 'Пункт первый')


class UnwrapMathWrappedTablesTests(SimpleTestCase):
    """Scale-up: Overleaf Archive 3, атлас "Ловушка №1" — 61 из 164 таблиц
    целиком внутри $/$$, KaTeX их не осилит."""

    def test_unwraps_double_dollar_table(self):
        text = '$$\\begin{tabular}{c|c}A & B\\\\\\end{tabular}$$'
        result = unwrap_math_wrapped_tables(text)
        self.assertEqual(result, '\\begin{tabular}{c|c}A & B\\\\\\end{tabular}')

    def test_unwraps_single_dollar_table(self):
        text = '$\\begin{tabular}{c}A\\end{tabular}$'
        result = unwrap_math_wrapped_tables(text)
        self.assertEqual(result, '\\begin{tabular}{c}A\\end{tabular}')

    def test_strips_orphaned_text_command_inside_unwrapped_table(self):
        # Живой дефект, найденный на реальной задаче #41535: \text{} внутри
        # таблицы имел смысл только пока таблица была математикой.
        text = '$$\\begin{tabular}{l|c}\\text{День} & \\text{Число}\\\\\\end{tabular}$$'
        result = unwrap_math_wrapped_tables(text)
        self.assertNotIn('\\text{', result)
        self.assertIn('День & Число', result)

    def test_leaves_real_math_untouched(self):
        text = 'Цена $P^*=10$ и объём $Q^*=5$.'
        self.assertEqual(unwrap_math_wrapped_tables(text), text)

    def test_real_archive3_problem_41535_table_renders_clean(self):
        text = (
            'Минимальное число медсестёр на смене:\n\n'
            '$$\\begin{tabular}{l | c}\n'
            '\\text{День недели} & \\text{Минимальное число медсестёр на смене} \\\\\n'
            '\\hline\n'
            '\\text{понедельник} & 10 \\\\\n'
            '\\text{вторник} & 12 \\\\\n'
            '\\end{tabular}$$'
        )
        result = convert_text_field(text)
        self.assertNotIn('\\text{', result['text_md'])
        self.assertIn('| День недели | Минимальное число медсестёр на смене |', result['text_md'])
        self.assertIn('| понедельник | 10 |', result['text_md'])
        self.assertFalse(result['complex_table'])


class ReconstructOrphanedTabularTests(SimpleTestCase):
    """Scale-up: МатЭк, атлас "Главный сюрприз" — 46 задач без обёртки
    \\begin{tabular}{...}, остались висячие \\hline и &."""

    def test_wraps_orphaned_matrix_game_table(self):
        # Живой пример — задача #30026 МатЭк.
        text = (
            'Найдите все равновесия в чистых и смешанных стратегиях в этой игре:\n\n'
            ' \\hline\n& L & R & C\n \\hline\nA & 6; 6 & 0; 0 & 7; 2\n \\hline\nB & 0; 0 & 4; 4 & 5; 1'
        )
        result = reconstruct_orphaned_tabular(text)
        self.assertIn('\\begin{tabular}', result)
        self.assertIn('\\end{tabular}', result)
        converted, complex_found = convert_tables(result)
        self.assertFalse(complex_found)
        self.assertIn('|  | L | R | C |', converted)
        self.assertIn('| A | 6; 6 | 0; 0 | 7; 2 |', converted)

    def test_does_not_touch_text_with_properly_wrapped_table(self):
        text = '\\begin{tabular}{|l|}\\hline X\\hline\\end{tabular}'
        self.assertEqual(reconstruct_orphaned_tabular(text), text)

    def test_leaves_plain_text_with_ampersand_untouched(self):
        # Одна строка с '&', без второй строки — недостаточно сигнала,
        # чтобы уверенно реконструировать таблицу.
        text = 'Условие: A & B — это два актива, не таблица.'
        self.assertEqual(reconstruct_orphaned_tabular(text), text)


class TabularMissingRowSeparatorsTests(SimpleTestCase):
    """Scale-up: Overleaf Archive 3, атлас "Ловушка №2" — 147 из 164 задач,
    построчные \\\\ срезаны, строки таблицы разделены пустыми строками."""

    def test_reconstructs_rows_from_blank_lines(self):
        # Живой пример — задача #43945 МатЭк/Archive 3.
        text = (
            '\\begin{tabular}{c|ccc}\n'
            'Доходность & Сценарий 1 & Сценарий 2 & Сценарий 3 \n\n'
            '\\hline\n'
            'Актив A & +60\\% & -30\\% & -10\\% \n\n'
            'Актив B & -20\\% & +40\\% & +10\\% \n\n'
            '\\end{tabular}'
        )
        result, complex_found = convert_tables(text)
        self.assertFalse(complex_found)
        self.assertIn('| Доходность | Сценарий 1 | Сценарий 2 | Сценарий 3 |', result)
        self.assertIn('| Актив A | +60\\% | -30\\% | -10\\% |', result)
        self.assertIn('| Актив B | -20\\% | +40\\% | +10\\% |', result)

    def test_single_row_body_left_alone(self):
        # Одна строка (после снятия \\hline) — нечего реконструировать,
        # таблица так и останется без разделителей, но и не пострадает.
        text = '\\begin{tabular}{c}\nОдна строка без пары\n\\end{tabular}'
        result, complex_found = convert_tables(text)
        self.assertIn('Одна строка без пары', result)


class StripMulticolsWrapperTests(SimpleTestCase):
    """Scale-up: Overleaf Archive 3, атлас — 243 задачи, multicols — вёрстка
    вариантов ответа в колонки, не таблица."""

    def test_removes_wrapper_keeps_content(self):
        text = '\\begin{multicols}{2}а) Вариант 1\nб) Вариант 2\\end{multicols}'
        result = strip_multicols_wrapper(text)
        self.assertNotIn('multicols', result)
        self.assertIn('а) Вариант 1', result)
        self.assertIn('б) Вариант 2', result)


class StripCenterAndParTests(SimpleTestCase):
    """Scale-up: ЛЭШ Гамма — живой пример: \\par и \\begin{center}...
    \\end{center} вокруг \\includegraphics оставались сырым текстом."""

    def test_par_removed(self):
        text = strip_junk_commands('Первая часть.\\par\nВторая часть.')
        self.assertNotIn('\\par', text)

    def test_center_wrapper_removed_keeps_content(self):
        from problems.corpus_converter.core import strip_center_wrapper
        text = '\\begin{center}\n\\includegraphics{img.png}\n\\end{center}'
        result = strip_center_wrapper(text)
        self.assertNotIn('center', result)
        self.assertIn('\\includegraphics{img.png}', result)


class StripHypertargetTests(SimpleTestCase):
    """Scale-up: Overleaf Archive 3, атлас — 85 вхождений \\hypertarget."""

    def test_keeps_visible_text_drops_anchor_id(self):
        text = '\\hypertarget{sec1}{Раздел про монополию}'
        self.assertEqual(strip_hypertarget(text), 'Раздел про монополию')


class StripJunkCommandsWithArgTests(SimpleTestCase):
    """Scale-up: ЛЭШ Гамма — живой пример \\vspace{0.5em} между подпунктами."""

    def test_removes_vspace_with_length_argument(self):
        text = 'Первая часть.\\vspace{0.5em}\n\nВторая часть.'
        result = strip_junk_commands(text)
        self.assertNotIn('\\vspace', result)
        self.assertIn('Первая часть.', result)
        self.assertIn('Вторая часть.', result)

    def test_removes_hspace_with_length_argument(self):
        text = 'Слева\\hspace{1cm}справа'
        result = strip_junk_commands(text)
        self.assertNotIn('\\hspace', result)


class RealDataRegressionTests(SimpleTestCase):
    """Живые задачи из базы (id по МатЭк/Archive 3), зафиксированные во
    время расширения конвертера 2026-08-26 — защита от регрессии на
    реальных, а не упрощённых текстах."""

    def test_matek_orphan_table_25_full_field(self):
        # Задача #30025 МатЭк — реконструкция без готового \\hline в начале.
        text = (
            'Вопрос: с какой вероятностью может играться A в равновесии в данной игре:\n\n\n'
            '\\hline\n & A & B & C\n \\hline\na & 6; 6 & 0; 0 & 0; 0\n \\hline\n'
            'b & 0; 0 & 4; 4 & 0; 0\n \\hline\nc & 0; 0 & 0; 0 & 2; 2'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertIn('|  | A | B | C |', result['text_md'])
        self.assertIn('| c | 0; 0 | 0; 0 | 2; 2 |', result['text_md'])

    def test_archive3_problem_43945_preserves_math_and_converts_table(self):
        text = (
            'Доходности активов заданы таблицей:\n\n'
            '\\begin{tabular}{c|ccc}\n'
            'Доходность & Сценарий 1 & Сценарий 2 & Сценарий 3 \n\n'
            '\\hline\n'
            'Актив $A$ & $+60\\%$ & $-30\\%$ & $-10\\%$ \n\n'
            'Актив $B$ & $-20\\%$ & $+40\\%$ & $+10\\%$ \n\n'
            '\\end{tabular}\n\n'
            'коэффициентом оптимизма $\\alpha \\in [0,1]$:\n\\[\nH=\\alpha \\cdot \\max\\{R_1,R_2,R_3\\}\n\\]'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertIn('| Доходность | Сценарий 1 | Сценарий 2 | Сценарий 3 |', result['text_md'])
        self.assertIn('$\\alpha \\in [0,1]$', result['text_md'])
        self.assertIn('\\[\nH=\\alpha \\cdot \\max\\{R_1,R_2,R_3\\}\n\\]', result['text_md'])
