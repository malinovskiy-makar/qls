from django.test import SimpleTestCase

from problems.corpus_converter.criteria import parse_shkolkovo_criteria, parse_solvehub_criteria


class ParseShkolkovoCriteriaTests(SimpleTestCase):
    def test_parses_itemize_blocks_per_part_with_points(self):
        text = (
            '\\textbf{(a)}\n'
            '\\begin{itemize}\n'
            '\\item 3 балла за верное определение картеля.\n'
            '\\item 1 балл за пример.\n'
            '\\end{itemize}\n'
            '\\textbf{(б)}\n'
            '\\begin{itemize}\n'
            '\\item 2 балла за формулу.\n'
            '\\end{itemize}'
        )
        result = parse_shkolkovo_criteria(text)
        self.assertEqual(len(result['criteria']), 3)
        self.assertEqual(result['criteria'][0]['max_points'], 3.0)
        self.assertIn('верное определение картеля', result['criteria'][0]['description'])
        self.assertTrue(result['criteria'][0]['name'].startswith('(a)'))
        self.assertEqual(result['criteria'][2]['max_points'], 2.0)
        self.assertTrue(result['criteria'][2]['name'].startswith('(б)'))

    def test_orders_criteria_sequentially(self):
        text = (
            '\\textbf{(a)}\\begin{itemize}\\item 1 балл за X.\\item 2 балла за Y.\\end{itemize}'
        )
        result = parse_shkolkovo_criteria(text)
        self.assertEqual([c['order'] for c in result['criteria']], [0, 1])

    def test_no_points_found_warns_and_leaves_points_none(self):
        text = '\\textbf{(a)}\\begin{itemize}\\item за верный ответ без указания баллов.\\end{itemize}'
        result = parse_shkolkovo_criteria(text)
        self.assertIsNone(result['criteria'][0]['max_points'])
        self.assertTrue(any('без баллов' in w for w in result['warnings']))

    def test_empty_criteria_tex_returns_empty(self):
        result = parse_shkolkovo_criteria('')
        self.assertEqual(result['criteria'], [])
        self.assertEqual(result['warnings'], [])

    def test_points_singular_and_plural_forms(self):
        text = '\\textbf{(a)}\\begin{itemize}\\item 1 балл за A.\\item 5 баллов за B.\\end{itemize}'
        result = parse_shkolkovo_criteria(text)
        self.assertEqual(result['criteria'][0]['max_points'], 1.0)
        self.assertEqual(result['criteria'][1]['max_points'], 5.0)

    def test_subsection_shape_is_now_recognized(self):
        # Раньше этот тест закреплял ОГРАНИЧЕНИЕ: доминирующая форма
        # Школково — \subsection*{(метка)} — не разбиралась вовсе. Сессия
        # 29.08 сняла ограничение: заголовок пункта распознаётся в шести
        # формах команд, и таких задач 319.
        text = '\\subsection*{(a)}\\begin{itemize}\\item 3 балла за верный ответ.\\end{itemize}'
        result = parse_shkolkovo_criteria(text)
        self.assertEqual(len(result['criteria']), 1)
        self.assertEqual(result['criteria'][0]['max_points'], 3.0)

    def test_unrecognized_shape_warns_when_zero_criteria_found(self):
        # Непустой criteria_tex без списка — критерии написаны прозой.
        # Парсер обязан честно предупредить, а не выдумывать разбиение.
        text = 'Выставлялось по 5 баллов за каждый верный аргумент.'
        result = parse_shkolkovo_criteria(text)
        self.assertEqual(result['criteria'], [])
        self.assertTrue(any('прозой' in w for w in result['warnings']))

    def test_recognized_shape_does_not_warn(self):
        text = '\\textbf{(a)}\\begin{itemize}\\item 3 балла за верный ответ.\\end{itemize}'
        result = parse_shkolkovo_criteria(text)
        self.assertEqual(len(result['criteria']), 1)
        self.assertFalse(any('не распознано ни одного критерия' in w for w in result['warnings']))


class ParseSolvehubCriteriaTests(SimpleTestCase):
    """Real-data фикстуры — задачи SolveHub с диска (2026-08-26), см. отчёт
    reports/corpus_converter_scaleup/report.md."""

    def test_empty_answer_returns_empty(self):
        result = parse_solvehub_criteria('')
        self.assertEqual(result['criteria'], [])
        self.assertEqual(result['warnings'], [])

    def test_no_criteria_header_returns_empty_no_warning(self):
        result = parse_solvehub_criteria('Ответ: 42. Решение простое.')
        self.assertEqual(result['criteria'], [])
        self.assertEqual(result['warnings'], [])

    def test_real_task_6371_numbered_items_with_signed_points(self):
        text = (
            'Ответ готов.\n\n$\\quad$ \n\n***Критерии****:*\n\n'
            '*1)  Дан ответ для долгосрочного увеличения* $Y \\ (33,1\\%)$ *(*$+5$ *баллов)*\n\n'
            '*2) Найдено увеличение денежной массы* $(33,1\\%)$  *(*$+5$ *баллов)*\n\n'
            '*3) Выписан SRAS* $(kP^2)$  *(*$+5$ *баллов)*\n\n'
            '*4) Найден уровень цен в* $SR$  $(1,1P)$  *(* $+8$  *баллов)*\n\n'
            '*5) Получен ответ* *(* $+5$  *баллов)*'
        )
        result = parse_solvehub_criteria(text)
        self.assertEqual(len(result['criteria']), 5)
        self.assertEqual([c['max_points'] for c in result['criteria']], [5.0, 5.0, 5.0, 8.0, 5.0])
        self.assertEqual([c['order'] for c in result['criteria']], [0, 1, 2, 3, 4])

    def test_real_task_6347_dash_items_with_negative_points(self):
        text = (
            'Ответ 200.\n\n'
            '***Критерии****: За пункт  дается 20 баллов.*\n\n'
            '*-Если нет* $mpc$ *в потреблении* $-15$ *баллов*\n\n'
            '*-Если не учли в потреблении* $-10$ *баллов*\n\n'
            '*-Ставка учтена не в процентных пунктах* $-5$ *баллов*'
        )
        result = parse_solvehub_criteria(text)
        self.assertEqual(len(result['criteria']), 3)
        self.assertEqual([c['max_points'] for c in result['criteria']], [-15.0, -10.0, -5.0])

    def test_unstructured_prose_warns_when_header_found_but_no_items(self):
        # Живой пример #2787: заголовок "Критерии проверки:" есть, но нет
        # ни одного пункта вида "N)"/"-" с баллами в $...$ — сплошная проза.
        text = 'Критерии проверки:\n\nПолностью решённой считалась задача, если...'
        result = parse_solvehub_criteria(text)
        self.assertEqual(result['criteria'], [])
        self.assertTrue(any('не распознано ни одного пункта' in w for w in result['warnings']))

    def test_criteria_word_as_ordinary_term_gives_no_false_items(self):
        # Живой пример #5578: "Критерии оптимума для функций полезности" —
        # обычный экономический термин, не заголовок баллов. Парсер не
        # обязан отличить это семантически, но не должен извлечь мусор.
        text = 'Критерии оптимума для функций полезности Кобба-Дугласа: $P_XX_1=P_YY_1$.'
        result = parse_solvehub_criteria(text)
        self.assertEqual(result['criteria'], [])

    def test_declined_word_form_does_not_match_as_header(self):
        # Живой пример #3609: "критериям" (дательный падеж) — обычная
        # лексика про ранжирование, не заголовок критериев оценивания.
        text = 'По каждому из критериев institut X превосходит institut Y.'
        result = parse_solvehub_criteria(text)
        self.assertEqual(result['criteria'], [])
        self.assertEqual(result['warnings'], [])


class ParseSolvehubCriteriaMultiHeaderDefectTests(SimpleTestCase):
    """Дефект 3, найден ревью 2026-08-26: задача #3498 — three-part answer
    "1) ... 2) ... 3) ..." с ТРЕМЯ отдельными разделами «Критерии» (по
    одному на часть). Раньше искали только первый заголовок и сканировали
    до конца answer_md — regex «N)» цеплял границы частей 2 и 3 как будто
    это пункты критериев, а настоящие (текстом, без "N)"/"-") критерии
    части 1 терялись без единого warning. Выжимка ниже сохраняет реальную
    структуру #3498 (номерованные части + три заголовка «Критерии»), но
    короче полного answer_md (8605 симв. в оригинале)."""

    REAL_STRUCTURE_EXCERPT = (
        '1) Первое решение $\\pi = 100$.\n\n'
        'Ответ: $15$  недель - $1$  балл\n\n'
        'Критерии при отличающемся решении:\n\n'
        '$1$  балл за весь пункт – если потеряно условие А.\n\n'
        '$1$  балл за весь пункт – если потеряно условие Б.\n\n'
        '2) Второе решение начинается здесь, с формулами '
        '$\\pi = 44400$ −$1$ балл и другими деталями.\n\n'
        'Критерии в случае неправильных решений:\n\n'
        'Ответ «неверно» оценивался в $0$ баллов.\n\n'
        '3) Третье решение теперь начинается тут.\n\n'
        '***Критерии оценивания:***\n\n'
        'За полностью правильное решение ставилось $3$ балла.'
    )

    def test_no_false_criteria_stolen_from_next_part_boundaries(self):
        # Раньше здесь фабриковались 2 "критерия" из текста частей 2/3.
        result = parse_solvehub_criteria(self.REAL_STRUCTURE_EXCERPT)
        self.assertEqual(result['criteria'], [])

    def test_warns_about_each_disqualified_part_boundary_section(self):
        result = parse_solvehub_criteria(self.REAL_STRUCTURE_EXCERPT)
        boundary_warnings = [w for w in result['warnings'] if 'границы частей' in w]
        self.assertEqual(len(boundary_warnings), 2)
        self.assertTrue(any('"2)"' in w for w in boundary_warnings))
        self.assertTrue(any('"3)"' in w for w in boundary_warnings))

    def test_warns_about_unclaimed_points_in_part_one_real_criteria(self):
        # Часть 1 несёт настоящие критерии текстом без "N)"/"-" — не
        # извлекаются структурно, но обязаны быть видны как warning, а не
        # молчание (это и есть эвристика-страховка из брифа).
        result = parse_solvehub_criteria(self.REAL_STRUCTURE_EXCERPT)
        unclaimed = [w for w in result['warnings'] if 'вне извлечённых критериев' in w]
        self.assertTrue(any('условие А' in w for w in unclaimed))
        self.assertTrue(any('условие Б' in w for w in unclaimed))



class ShkolkovoWiderHeadersTests(SimpleTestCase):
    r"""Расширение парсера: 319 задач Школково имели настоящий список.

    Прежний парсер брал ровно одну форму заголовка пункта —
    `\textbf{(метка)}` сразу перед `\begin{itemize}`. Свип по 836
    непустым `criteria_tex` показал, что это меньшинство: те же по сути
    критерии пишутся ещё как `\subsection*{(а)}` и `\textbf{Пункт (а)}
    (6 баллов):`, а баллы стоят не только в начале пункта, но и в конце
    (`~--- 2 балла`). Границы блоков ищутся ПО ЗАГОЛОВКАМ, а не жадным
    захватом (тот же урок, что у SolveHub #3498).
    """

    def test_167074_subsection_header_with_itemize(self):
        tex = ('\\subsection*{(а)}\n\\begin{itemize}\n'
               '\\item 2 балла за запись прибыли фирмы.\n'
               '\\item 1 балл за нахождение оптимального $L$.\n'
               '\\end{itemize}\n')
        result = parse_shkolkovo_criteria(tex)
        self.assertEqual(len(result['criteria']), 2)
        self.assertEqual([c['max_points'] for c in result['criteria']], [2.0, 1.0])
        self.assertTrue(result['criteria'][0]['name'].startswith('(а)'))

    def test_167118_points_at_end_of_item(self):
        r"""`~--- 2 балла` в КОНЦЕ пункта — самая частая форма семейства."""
        tex = ('\\textbf{Пункт (а)} (6 баллов):\n\\begin{itemize}\n'
               '\\item Расчет прибыли Беты и выбор объема~--- 2 балла\n'
               '\\item За верные расчёты цен в каждом регионе~--- по 2 балла\n'
               '\\end{itemize}\n')
        result = parse_shkolkovo_criteria(tex)
        self.assertEqual(len(result['criteria']), 2)
        self.assertEqual([c['max_points'] for c in result['criteria']], [2.0, 2.0])

    def test_enumerate_is_read_like_itemize(self):
        tex = ('\\textbf{(б)}\n\\begin{enumerate}\n'
               '\\item 3 балла за верный график.\n\\end{enumerate}\n')
        result = parse_shkolkovo_criteria(tex)
        self.assertEqual(len(result['criteria']), 1)
        self.assertEqual(result['criteria'][0]['max_points'], 3.0)

    def test_points_written_as_abbreviation(self):
        r"""`2~б.` — так пишут баллы у #175879, слова «балл» там нет вовсе."""
        tex = ('\\textbf{а)}\n\\begin{itemize}\n'
               '\\item 2~б. Полностью описан механизм.\n\\end{itemize}\n')
        result = parse_shkolkovo_criteria(tex)
        self.assertEqual(len(result['criteria']), 1)
        self.assertEqual(result['criteria'][0]['max_points'], 2.0)

    def test_two_parts_do_not_bleed_into_each_other(self):
        """Граница по заголовку: пункты (б) не приписываются к (а)."""
        tex = ('\\subsection*{(а)}\n\\begin{itemize}\n\\item 2 балла за первое.\n'
               '\\end{itemize}\n\\subsection*{(б)}\n\\begin{itemize}\n'
               '\\item 5 баллов за второе.\n\\end{itemize}\n')
        result = parse_shkolkovo_criteria(tex)
        names = [c['name'] for c in result['criteria']]
        self.assertEqual(len(names), 2)
        self.assertIn('(а)', names[0])
        self.assertIn('(б)', names[1])
        self.assertNotIn('второе', names[0])

    def test_list_without_any_header_still_read(self):
        """Список без заголовка пункта — критерии всё равно настоящие."""
        tex = ('\\begin{itemize}\n\\item 4 балла за вывод.\n'
               '\\item 1 балл за график.\n\\end{itemize}\n')
        result = parse_shkolkovo_criteria(tex)
        self.assertEqual(len(result['criteria']), 2)

    def test_criteria_none_marker_is_empty_without_warning(self):
        """`% criteria: none` — это «критериев нет», а не «не разобрали».

        110 задач из 836. Считать их неудачей парсера значит завышать
        объём непокрытого."""
        result = parse_shkolkovo_criteria('% criteria: none')
        self.assertEqual(result['criteria'], [])
        self.assertEqual(result['warnings'], [])

    def test_free_prose_is_not_guessed(self):
        """Проза без списка — баллы НЕ выдумываются, идёт предупреждение.

        Угадывать разбиение свободного текста на критерии запрещено: это
        было бы выдуманное, а не импортированное знание."""
        tex = ('В задаче есть два сложных момента. Незначительная '
               'арифметическая ошибка оценивается в 1 балл в каждом пункте.')
        result = parse_shkolkovo_criteria(tex)
        self.assertEqual(result['criteria'], [])
        self.assertTrue(result['warnings'])

    def test_old_textbf_itemize_shape_still_works(self):
        """Регрессия: 45 уже разбиравшихся задач не должны отвалиться."""
        tex = ('\\textbf{(а)}\\begin{itemize}\\item 3 балла за вывод.'
               '\\end{itemize}')
        result = parse_shkolkovo_criteria(tex)
        self.assertEqual(len(result['criteria']), 1)
        self.assertEqual(result['criteria'][0]['max_points'], 3.0)

    def test_item_without_points_still_becomes_criterion_with_warning(self):
        """Пункт без баллов — критерий есть, балл неизвестен.

        Прежнее поведение, и его надо сохранить: терять пункт нельзя,
        а выдумывать за него балл — тем более."""
        tex = ('\\textbf{(а)}\n\\begin{itemize}\n'
               '\\item За аккуратность оформления.\n\\end{itemize}\n')
        result = parse_shkolkovo_criteria(tex)
        self.assertEqual(len(result['criteria']), 1)
        self.assertIsNone(result['criteria'][0]['max_points'])
        self.assertTrue(result['warnings'])

    def test_167105_nested_list_does_not_leak_raw_latex(self):
        r"""Вложенный список: внешний `\item` — заголовок, а не критерий.

        43 задачи из 362 разобранных получали в имя критерия сырой
        `\begin{itemize}`: нежадный `(.*?)` закрывал внешний список на
        `\end` ВНУТРЕННЕГО."""
        tex = ('\\begin{itemize}\n'
               '\\item [А)] Определите функции спроса и предложения. (6 баллов)\n'
               '\\begin{itemize}\n'
               '\\item 3 балла за спрос.\n'
               '\\item 3 балла за предложение.\n'
               '\\end{itemize}\n'
               '\\end{itemize}')
        result = parse_shkolkovo_criteria(tex)
        for criterion in result['criteria']:
            self.assertNotIn('\\begin{', criterion['name'])
            self.assertNotIn('\\end{', criterion['name'])
        self.assertEqual([c['max_points'] for c in result['criteria']], [3.0, 3.0])
        self.assertTrue(all('(А)' in c['name'] for c in result['criteria']))
