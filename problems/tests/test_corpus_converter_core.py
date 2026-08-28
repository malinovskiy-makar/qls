from django.test import SimpleTestCase

from problems.corpus_converter.core import (
    wrap_bare_environments, protect_math, restore_math,
    normalize_dashes, normalize_quotes, find_images, convert_text_field,
    convert_problem, strip_control_and_bom_chars, unwrap_math_wrapped_tables,
    reconstruct_orphaned_tabular, strip_multicols_wrapper, strip_hypertarget,
    strip_junk_commands, convert_tables, strip_center_wrapper,
    reconstruct_bare_ampersand_table, has_unreconstructed_bare_ampersand_rows,
    reconstruct_cases_row_separators, has_broken_cases_rows,
    may_render_as_markdown,
)


class MayRenderAsMarkdownTests(SimpleTestCase):
    """Фаза 2 сессии 2026-08-27: фильтр «сложную таблицу не рендерим»
    обязан быть частью логики, а не пунктом, который надо не забыть
    проверить руками в боевой команде рендера."""

    def test_forbids_markdown_for_complex_table(self):
        # \multicolumn — конвертер такое не разбирает, задача в очереди
        # на ручной разбор (manual_review_queue.md).
        result = convert_problem(
            '\\begin{tabular}{ll}\\multicolumn{2}{c}{Шапка} \\\\ a & b\\end{tabular}'
        )
        self.assertTrue(result['complex_table'])
        self.assertFalse(may_render_as_markdown(result))

    def test_forbids_markdown_for_broken_cases(self):
        result = convert_problem('$$\\begin{cases}a & x<1 b & x\\ge 1\\end{cases}$$')
        self.assertTrue(result['complex_table'])
        self.assertFalse(may_render_as_markdown(result))

    def test_allows_markdown_for_clean_problem(self):
        result = convert_problem('Найдите $Q$, если $P = 10$.')
        self.assertFalse(result['complex_table'])
        self.assertTrue(may_render_as_markdown(result))


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

    def test_table_delimiter_row_untouched(self):
        # Дефект, найден ревью 2026-08-26 при подготовке страницы визуального
        # просмотра: "---" в разделителе markdown-таблицы превращался в "—",
        # markdown-it переставал узнавать таблицу вовсе (весь текст рендерился
        # одним <p> с сырыми "|" вместо <table> — то, что видел бы студент).
        line = '| --- | --- | --- |'
        self.assertEqual(normalize_dashes(line), line)

    def test_table_delimiter_row_untouched_inside_full_table(self):
        text = (
            '| Показатель | Значение |\n'
            '| --- | --- |\n'
            '| Q | 10 |'
        )
        self.assertEqual(normalize_dashes(text), text)

    def test_prose_dashes_still_normalized_around_table(self):
        # Разделитель не трогается, а обычное тире рядом — как обычно.
        text = 'До таблицы---тире.\n| --- | --- |\nПосле---тире.'
        result = normalize_dashes(text)
        self.assertIn('До таблицы—тире.', result)
        self.assertIn('| --- | --- |', result)
        self.assertIn('После—тире.', result)

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

    def test_reconstructed_table_actually_renders_as_html_table(self):
        # Дефект, найден ревью 2026-08-26 (задача #33817, "Найдите все
        # равновесия Нэша..."): normalize_dashes портила служебный "---"
        # разделитель markdown-таблицы, markdown-it переставал видеть
        # таблицу вовсе — прод-рендерер показал бы сплошной <p> с "|" вместо
        # <table>. Проверяем ИМЕННО прод-функцией render_markdown, не только
        # промежуточный text_md, — это и есть то, что увидит студент.
        from problems.rendering import render_markdown
        text = (
            'Найдите все равновесия Нэша в следующей игре:\n\n\n\n'
            ' & $ s_1 $ & $ s_2 $\n\n'
            ' $t_1$ & (100, 10) & (10, 11)\n\n'
            ' $t_2$ & (110, 5) & (15, 5)'
        )
        result = convert_text_field(text)
        html = render_markdown(result['text_md'])
        self.assertIn('<table>', html)
        self.assertIn('<td>$t_1$</td>', html)
        self.assertIn('<td>(100, 10)</td>', html)


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


class ReconstructBareAmpersandTableTests(SimpleTestCase):
    """Scale-up ревью 2026-08-26: Archive 3, задача #33817 — голые
    '&'-строки без \\hline и без \\begin{tabular}, замерено 19 задач по
    всей базе Archive 3 после исключения ложных срабатываний внутри
    \\begin{cases}."""

    def test_wraps_bare_rows_without_hline(self):
        text = ' & A & B\n\nстрока1 & 1 & 2\n\nстрока2 & 3 & 4'
        result = reconstruct_bare_ampersand_table(text)
        self.assertIn('\\begin{tabular}', result)
        self.assertIn('\\end{tabular}', result)

    def test_does_not_touch_text_inside_cases_block(self):
        # Кусочная функция через '&' — это математика, не таблица;
        # оборачивать её в tabular исказило бы смысл.
        text = '$$\\begin{cases}0,5x & x<1\\\\1,5x-0,5 & x\\ge 1\\end{cases}$$'
        self.assertEqual(reconstruct_bare_ampersand_table(text), text)

    def test_single_row_left_alone(self):
        text = 'Одна строка & без пары'
        self.assertEqual(reconstruct_bare_ampersand_table(text), text)

    def test_does_not_touch_already_wrapped_tabular(self):
        text = '\\begin{tabular}{|l|}\\hline X\\hline\\end{tabular}'
        self.assertEqual(reconstruct_bare_ampersand_table(text), text)


class HasUnreconstructedBareAmpersandRowsTests(SimpleTestCase):
    """Страховка: то, что reconstruct_bare_ampersand_table не смог
    обработать сам (кусочная функция без обёртки \\begin{cases}, либо
    меньше двух строк), обязано быть замечено, а не пройти молча."""

    def test_flags_bare_rows_inside_cases_block_left_untouched(self):
        # Кусочная функция с ТЕМ ЖЕ дефектом, что и таблицы Archive 3:
        # построчные разделители внутри \begin{cases} срезаны, строки
        # разошлись пустыми строками вместо '\\'. reconstruct_bare_
        # ampersand_table намеренно её не трогает (это не таблица) — но
        # молчать об оставшемся мусоре нельзя.
        text = '\\begin{cases}0,5x & x<1\n\n1,5x-0,5 & x\\ge 1\\end{cases}'
        self.assertTrue(has_unreconstructed_bare_ampersand_rows(text))

    def test_does_not_flag_after_successful_reconstruction(self):
        text = ' & A & B\n\nстрока1 & 1 & 2\n\nстрока2 & 3 & 4'
        reconstructed = reconstruct_bare_ampersand_table(text)
        self.assertFalse(has_unreconstructed_bare_ampersand_rows(reconstructed))

    def test_does_not_flag_plain_text_without_ampersand(self):
        self.assertFalse(has_unreconstructed_bare_ampersand_rows('Обычный текст без таблиц.'))

    def test_full_pipeline_now_reconstructs_cases_with_blank_line_rows(self):
        # Раньше (до reconstruct_cases_row_separators) этот cases не
        # чинился, только флагировался — теперь пустая строка между
        # строками cases однозначно реконструируется (см. новый класс
        # ReconstructCasesRowSeparatorsTests ниже), поэтому и полный
        # конвейер больше не должен на нём предупреждать.
        text = '\\begin{cases}0,5x & x<1\n\n1,5x-0,5 & x\\ge 1\\end{cases}'
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertNotIn('\\begin{cases}0,5x & x<1\n', result['text_md'])
        self.assertIn('0,5x & x<1 \\\\ 1,5x-0,5 & x\\ge 1', result['text_md'])

    def test_full_pipeline_warns_on_genuinely_ambiguous_cases_block(self):
        # Ни одной пустой строки — строки cases слиплись в одну без
        # единого разделителя, реконструировать однозначно нельзя.
        text = '\\begin{cases}0,5x & x<1 1,5x-0,5 & x\\ge 1\\end{cases}'
        result = convert_text_field(text)
        self.assertTrue(result['complex_table'])
        self.assertTrue(any('сломанный \\begin{cases}' in w for w in result['warnings']))


class ReconstructCasesRowSeparatorsTests(SimpleTestCase):
    """Ревью 2026-08-26 (владелец лично просмотрел review_samples.html):
    \\begin{cases} с потерянным построчным \\\\ — тот же баг импорта, что
    у таблиц, но сигнал — пустая строка, не '&' (живой пример #28255:
    строки вовсе без '&'). Честный пересчёт по всем 4 легаси-источникам
    показал вместо старых 164 гораздо больший масштаб — см. report.md."""

    def test_reconstructs_rows_with_ampersand_condition(self):
        text = '\\begin{cases}a & x<1\n\nb & x\\ge 1\\end{cases}'
        result = reconstruct_cases_row_separators(text)
        self.assertEqual(result, '\\begin{cases}a & x<1 \\\\ b & x\\ge 1\\end{cases}')

    def test_reconstructs_rows_without_ampersand(self):
        # Живой паттерн #28255: строки без единого '&', разделены запятой
        # внутри строки и пустой строкой между строками.
        text = '\\begin{cases}100-0.25x,0\\leq x\\leq 80\n\n160-x, 80\\leq x\\leq 160\\end{cases}'
        result = reconstruct_cases_row_separators(text)
        self.assertNotIn('\n\n', result)
        self.assertIn('100-0.25x,0\\leq x\\leq 80 \\\\ 160-x, 80\\leq x\\leq 160', result)

    def test_does_not_touch_already_correct_cases(self):
        text = '\\begin{cases}a & x<1\\\\b & x\\ge 1\\end{cases}'
        self.assertEqual(reconstruct_cases_row_separators(text), text)

    def test_single_segment_left_alone(self):
        # Нет пустой строки вовсе — реконструировать не из чего.
        text = '\\begin{cases}a & x<1\\end{cases}'
        self.assertEqual(reconstruct_cases_row_separators(text), text)

    def test_three_or_more_segments_reconstructed(self):
        text = '\\begin{cases}a\n\nb\n\nc\\end{cases}'
        result = reconstruct_cases_row_separators(text)
        self.assertEqual(result, '\\begin{cases}a \\\\ b \\\\ c\\end{cases}')

    def test_multiple_cases_blocks_in_one_text_each_handled(self):
        text = (
            'Первая: \\begin{cases}a\n\nb\\end{cases}. '
            'Вторая: \\begin{cases}c\n\nd\\end{cases}.'
        )
        result = reconstruct_cases_row_separators(text)
        self.assertIn('\\begin{cases}a \\\\ b\\end{cases}', result)
        self.assertIn('\\begin{cases}c \\\\ d\\end{cases}', result)


class ReconstructCasesRowsBySingleNewlineTests(SimpleTestCase):
    """Сессия 2026-08-27: второй сигнал границы строки, кроме пустой строки —
    одиночный `\\n`, подтверждённый количеством `&` в блоке. Строки cases
    в LaTeX идут через `&`: если сегментов после разбиения по `\\n` РОВНО
    столько же, сколько `&` в теле, это не догадка — количество `&`
    независимо подтверждает число строк (ровно тот же принцип, каким
    has_broken_cases_rows уже считает строки для проверки).

    Первая версия этого расширения (2026-08-27, до реализации) называла
    32 таких блока (19 Archive 3 + 13 МатЭк). Число не воспроизвелось:
    это была ошибка отчёта прошлой сессии — в карточку попала цифра от
    другого, более мягкого пробного скрипта (эвристика по словам-маркерам
    «если»/«иначе», без требования `&`), а не от строгого правила `&`,
    которое здесь реализовано. Проверка по точному правилу на актуальных
    данных даёт 7 блоков, все в Archive 3 — см. RealDataCasesRowsBySingle
    NewlineRegressionTests ниже."""

    def test_two_rows_confirmed_by_matching_ampersand_count(self):
        text = '\\begin{cases}a & x<1\n b & x\\ge 1\\end{cases}'
        result = reconstruct_cases_row_separators(text)
        self.assertEqual(result, '\\begin{cases}a & x<1 \\\\ b & x\\ge 1\\end{cases}')

    def test_three_rows_confirmed_by_matching_ampersand_count(self):
        text = '\\begin{cases}a & x<1\n b & x<2\n c & x\\ge 2\\end{cases}'
        result = reconstruct_cases_row_separators(text)
        self.assertEqual(
            result, '\\begin{cases}a & x<1 \\\\ b & x<2 \\\\ c & x\\ge 2\\end{cases}'
        )

    def test_does_not_apply_when_ampersand_count_does_not_match_segments(self):
        # 2 сегмента по '\n', но 3 '&' в теле — не совпадает, значит один
        # из переносов НЕ граница строки (например перенос длинной
        # формулы), а гадать, какой именно, нельзя.
        text = '\\begin{cases}a & x<1 & y<1\n b & x\\ge 1\\end{cases}'
        self.assertEqual(reconstruct_cases_row_separators(text), text)

    def test_does_not_apply_without_ampersand_at_all(self):
        # Правило работает только через '&' — без него подтвердить число
        # строк независимо нечем, это другой (уже реализованный) случай
        # пустой строки, не одиночного переноса.
        text = '\\begin{cases}a\n b\\end{cases}'
        self.assertEqual(reconstruct_cases_row_separators(text), text)

    def test_blank_line_case_still_takes_priority(self):
        # Если пустая строка есть — реконструкция идёт по ней (прежнее
        # правило), новая ветка по '&' не должна вмешиваться.
        text = '\\begin{cases}a & x<1\n\nb & x\\ge 1\\end{cases}'
        result = reconstruct_cases_row_separators(text)
        self.assertEqual(result, '\\begin{cases}a & x<1 \\\\ b & x\\ge 1\\end{cases}')


class HasBrokenCasesRowsTests(SimpleTestCase):
    """Проверка ПО ПРАВИЛУ, а не по списку известных паттернов поломки:
    разделителей `\\\\` внутри cases обязано быть на единицу меньше, чем
    строк условий. Чем строки разделены на самом деле — неважно."""

    def test_flags_when_reconstruction_impossible(self):
        text = '\\begin{cases}a & x<1 b & x\\ge 1\\end{cases}'
        self.assertTrue(has_broken_cases_rows(text))

    def test_does_not_flag_after_successful_reconstruction(self):
        text = reconstruct_cases_row_separators('\\begin{cases}a\n\nb\\end{cases}')
        self.assertFalse(has_broken_cases_rows(text))

    def test_does_not_flag_well_formed_cases(self):
        text = '\\begin{cases}a & x<1\\\\b & x\\ge 1\\end{cases}'
        self.assertFalse(has_broken_cases_rows(text))

    def test_does_not_flag_text_without_cases(self):
        self.assertFalse(has_broken_cases_rows('Обычный текст.'))

    def test_flags_partially_lost_separators(self):
        # ГЛАВНОЕ, ради чего правило заменило прежнюю проверку: три строки
        # (три '&'), а разделитель всего один — второй потерян. Прежняя
        # проверка «есть ли хоть один \\» такое увидеть не могла в
        # принципе и пропускала молча.
        text = '\\begin{cases}a & x<1 \\\\ b & x<2 c & x<3\\end{cases}'
        self.assertTrue(has_broken_cases_rows(text))

    def test_flags_rows_glued_by_single_newline(self):
        # Строки разделены одиночным '\n' — реконструкция по пустой строке
        # такое не чинит, но правило видит поломку независимо от того,
        # ЧЕМ строки разделены (живой паттерн #29485 МатЭк).
        text = '\\begin{cases}30-4k,& k<3,\n 18,& k\\ge 3.\\end{cases}'
        self.assertTrue(has_broken_cases_rows(text))

    def test_flags_orphaned_line_skip_marker(self):
        # `\\[8pt]` потерял именно `\\`, остался голый `[8pt]` (живой
        # паттерн #43909 Archive 3) — разделителя нет, строк две.
        text = '\\begin{cases}12, & m<\\frac23,\n[8pt]\n6, & m\\ge\\frac23\\end{cases}'
        self.assertTrue(has_broken_cases_rows(text))

    def test_does_not_flag_single_row_cases(self):
        # Живой #28419 МатЭк: честная однострочная `\begin{cases} p \end{cases}`.
        # Прежняя проверка флагировала её ложно (нет `\\` — значит сломано).
        text = '\\begin{cases}\n p\n \\end{cases}'
        self.assertFalse(has_broken_cases_rows(text))

    def test_does_not_flag_row_wrapped_across_physical_lines(self):
        # Живой #41599 Archive 3: строк честные три, разделителя два,
        # просто третья строка перенесена на две физические. Считать
        # строки по '\n' здесь нельзя — правило и не считает, потому что
        # разделители в блоке есть.
        text = (
            '\\begin{cases}\n'
            '\\frac{I}{p_x}, p_x < \\frac{2}{5} \\\\\n'
            '[0;\\frac{I}{p_X}], p_x = \\frac{2}{5} \\\\\n'
            '0, p_x > \n \\frac{2}{5}\n'
            '\\end{cases}'
        )
        self.assertFalse(has_broken_cases_rows(text))


class RealDataCasesRegressionTests(SimpleTestCase):
    """Пять живых примеров ревью 2026-08-26 — по каждому подтверждена
    методология «откат фикса → тест краснеет → фикс восстановлен → тест
    зелёный»."""

    def test_archive3_41612_cases_with_blank_line_and_ampersand(self):
        text = (
            '\\[ U^\\theta(q,p) = \n'
            '\\begin{cases}\n'
            '\\theta\\sqrt{q} - p, & если покупатель приобретает товар \n\n'
            '0, & если отказывается от покупки\n'
            '\\end{cases} \\]'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn('\\theta\\sqrt{q} - p, & если покупатель приобретает товар \\\\', result['text_md'])
        self.assertIn('0, & если отказывается от покупки', result['text_md'])

    def test_matek_26337_cases_with_semicolon_and_ampersand(self):
        text = (
            '\\[\nQ(L,K) = min(L^2,K) =\n'
            '\\begin{cases}\n'
            'L^2 ; & L^2 \\leq K \n\n'
            'K; & L^2 > K\n'
            '\\end{cases}\n\\]'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn('L^2 ; & L^2 \\leq K \\\\ K; & L^2 > K', result['text_md'])

    def test_reshalki_47113_multiple_cases_blocks_in_one_field(self):
        # Решалки Олмат — источник, где баг раньше вообще не измерялся.
        text = (
            '$$\nTC(Q) = \n\\begin{cases}\n'
            ' 16Q + C, & если Q > 0 \n\n'
            ' 0, & если Q = 0\n'
            '\\end{cases}\n$$'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn('16Q + C, & если Q > 0 \\\\ 0, & если Q = 0', result['text_md'])

    def test_reshalki_47137_cases_inside_multicols(self):
        text = (
            '\\begin{multicols}{2}\n'
            '$$U_{м}=\\begin{cases}\n x_{м}, & x_{м}+x_{ж}\\leq1;\n\n'
            ' 0, & иначе\n\\end{cases}$$\n'
            '\\end{multicols}'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn('x_{м}, & x_{м}+x_{ж}\\leq1; \\\\ 0, & иначе', result['text_md'])
        self.assertNotIn('multicols', result['text_md'])

    def test_matek_28255_cases_without_any_ampersand(self):
        # Дефект, который старая страховка вообще не ловила: строки без
        # единого '&', разделены запятой и пустой строкой.
        text = (
            'Уравнение: $y=\\begin{cases}100-0.25x,0\\leq x\\leq 80\n\n'
            '160-x, 80\\leq x\\leq 160\\end{cases}$'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn('100-0.25x,0\\leq x\\leq 80 \\\\ 160-x, 80\\leq x\\leq 160', result['text_md'])

    def test_reshalki_47127_cases_is_reconstructed_and_not_flagged(self):
        # Владелец назвал #47127 как ещё один необнаруженный вариант
        # поломки cases. Проверка на живом тексте показала другое: cases
        # здесь чинится штатно (две строки, две '&', разделены пустой
        # строкой), предупреждения быть не должно. Настоящий дефект
        # #47127 — в другом месте, см. test_reshalki_47127_unbalanced_
        # display_math ниже. Тест закрепляет обе половины разбора, чтобы
        # правило инварианта не начало флагировать этот блок ложно.
        solution = (
            '$$\n\n \n\nОбе функции $MC$ убывают, значит, производим только на '
            'одном заводе. Сначала на втором, потом оставшееся -- на первом\n'
            '$$TC = \\begin{cases}\n'
            ' 16Q-0.25Q^2 & Q \\leq 32\n\n'
            ' 256+32(Q-32) -(Q-32)^2& Q \\in [32; 50]\n\n'
            ' \\end{cases}$$\n\n'
        )
        result = convert_text_field(solution)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn(
            '16Q-0.25Q^2 & Q \\leq 32 \\\\ 256+32(Q-32) -(Q-32)^2& Q \\in [32; 50]',
            result['text_md'],
        )


class RealDataCasesRowsBySingleNewlineRegressionTests(SimpleTestCase):
    """Сессия 2026-08-27, живые тексты из базы (только чтение, до правки
    кода) для трёх из семи подтверждённых блоков: разделены одиночным
    `\\n` без пустой строки, число сегментов подтверждено количеством `&`.
    Все три из Archive 3 — по факту, ни одного подтверждённого блока в
    МатЭк не оказалось (фикс-пак человека уже закрыл бо́льшую часть)."""

    def test_archive3_41824_two_row_cases_part_b(self):
        # Живой текст ProblemPart.statement, подпункт «б».
        text = '$\\begin{cases} TC=Q^2+100, & Q>0 \n TC=0, & Q=0 \\end{cases}$'
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn('TC=Q^2+100, & Q>0 \\\\ TC=0, & Q=0', result['text_md'])

    def test_archive3_41550_two_row_cases_with_text_command(self):
        # Живой фрагмент statement — v(x) кусочно-линейная функция полезности.
        text = (
            '$$\n'
            'v(x)= \\begin{cases}x, & \\text { если } x \\geq 0 \n'
            ' 2 x, & \\text { если } x<0\\end{cases}\n'
            '$$'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn(
            'x, & \\text { если } x \\geq 0 \\\\ 2 x, & \\text { если } x<0',
            result['text_md'],
        )

    def test_archive3_41236_three_row_cases_gini_coefficient(self):
        # Живой фрагмент statement — кусочно-линейная R(x), три строки.
        text = (
            '$$\n'
            'R(x)= \\begin{cases}\\frac{5}{7} \\cdot x & x \\in[0 ; 0.35 \\cdot \\sqrt{2}] \n'
            ' 0.32 \\cdot \\sqrt{2}-0.2 \\cdot x & x \\in[0.35 \\cdot \\sqrt{2} ; 0.6 \\cdot \\sqrt{2}] \n'
            ' 0.5 \\cdot \\sqrt{2}-0.5 \\cdot x & x \\in[0.6 \\cdot \\sqrt{2} ; \\sqrt{2}]\\end{cases}\n'
            '$$'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn(
            '\\frac{5}{7} \\cdot x & x \\in[0 ; 0.35 \\cdot \\sqrt{2}] \\\\ '
            '0.32 \\cdot \\sqrt{2}-0.2 \\cdot x & x \\in[0.35 \\cdot \\sqrt{2} ; 0.6 \\cdot \\sqrt{2}] \\\\ '
            '0.5 \\cdot \\sqrt{2}-0.5 \\cdot x & x \\in[0.6 \\cdot \\sqrt{2} ; \\sqrt{2}]',
            result['text_md'],
        )


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

    def test_archive3_problem_33817_bare_ampersand_matrix_game_table(self):
        # Дефект 1, найден ревью 2026-08-26: голые '&'-строки без \hline и
        # без \begin{tabular} — задача #33817 «Найдите все равновесия
        # Нэша...» — раньше проходила молча: не собиралась в таблицу, но
        # и не помечалась complex_table/warnings.
        text = (
            'Найдите все равновесия Нэша в следующей игре:\n\n\n\n'
            ' & $ s_1 $ & $ s_2 $ & $ s_3 $ & $ s_4 $ & $ s_5 $\n\n'
            ' $t_1$ & (100, 10) & (10, 11) & (7, 8) & (3, 10) & (20, 100)\n\n'
            ' $t_2$ & (110, 5) & (15, 5) & (8, 7) & (4, 4) & (30, 4)\n\n'
            ' $t_3$ & (10, 2) & (0, 4) & (3, 3) & (6, 2) & (20, 0)\n\n'
            ' $t_4$ & (200, 0) & (12, 12) & (5, 9) & (2, 10) & (40, 8)'
        )
        result = convert_text_field(text)
        self.assertFalse(result['complex_table'])
        self.assertEqual(result['warnings'], [])
        self.assertIn('| $t_1$ | (100, 10) | (10, 11) | (7, 8) | (3, 10) | (20, 100) |', result['text_md'])
        self.assertIn('| $t_4$ | (200, 0) | (12, 12) | (5, 9) | (2, 10) | (40, 8) |', result['text_md'])
        self.assertNotIn('\\begin{tabular}', result['text_md'])

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
