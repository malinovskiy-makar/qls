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

    def test_unrecognized_shape_warns_when_zero_criteria_found(self):
        # Реальная доминирующая форма Школково — \subsection*{(метка)}, а
        # не \textbf{(метка)} — парсер её не разбирает вовсе (вне рамок
        # этой fix-волны), но обязан честно предупредить, а не молчать.
        text = '\\subsection*{(a)}\\begin{itemize}\\item 3 балла за верный ответ.\\end{itemize}'
        result = parse_shkolkovo_criteria(text)
        self.assertEqual(result['criteria'], [])
        self.assertTrue(any('не распознано ни одного критерия' in w for w in result['warnings']))

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
