# -*- coding: utf-8 -*-
from django.test import SimpleTestCase

from problems.corpus_converter.lesh import parse_z_blocks, interpret_z_args


class ParseZBlocksTests(SimpleTestCase):
    def test_parses_simple_block_with_name_statement_subpoints(self):
        text = (
            '\\begin{document}\n'
            '\\z[Название]{Условие задачи.}{\n'
            '\\n Первый пункт;\n'
            '\\n Второй пункт;\n'
            '}\n'
            '\\end{document}'
        )
        blocks, warnings = parse_z_blocks(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(blocks), 1)
        parsed = interpret_z_args(blocks[0])
        self.assertEqual(parsed['name'], 'Название')
        self.assertEqual(parsed['statement'], 'Условие задачи.')
        self.assertEqual(parsed['subpoints'], ['Первый пункт', 'Второй пункт'])
        self.assertIsNone(parsed['points'])
        self.assertIsNone(parsed['source'])

    def test_ignores_z_mentions_in_header_comment(self):
        # Атлас: шапка каждого файла упоминает \\z трижды в комментарии-
        # инструкции — наивный grep даёт 187 вместо 152. Парсер считает
        # только между \\begin{document} и \\end{document}.
        text = (
            '% \\z{Текст} — задача без пунктов\n'
            '% \\z[Название][20 баллов]{Текст}\n'
            '\\begin{document}\n'
            '\\z{Единственная настоящая задача.}\n'
            '\\end{document}'
        )
        blocks, warnings = parse_z_blocks(text)
        self.assertEqual(len(blocks), 1)

    def test_balances_nested_braces_inside_argument(self):
        # Формула с {} внутри аргумента не должна оборвать чтение раньше времени.
        text = (
            '\\begin{document}\n'
            '\\z{Дано $C = 10 + 0{,}75Y_d$, где $Y_d$ доход.}\n'
            '\\end{document}'
        )
        blocks, warnings = parse_z_blocks(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(blocks), 1)
        parsed = interpret_z_args(blocks[0])
        self.assertIn('0{,}75Y_d', parsed['statement'])

    def test_unbalanced_braces_warn_and_skip_block(self):
        text = '\\begin{document}\n\\z{Незакрытая скобка\n\\end{document}'
        blocks, warnings = parse_z_blocks(text)
        self.assertEqual(blocks, [])
        self.assertTrue(any('несбалансированные скобки' in w for w in warnings))

    def test_argument_on_next_line_is_not_lost(self):
        # Живой дефект, найденный на реальном файле «Фискальная политика.tex»:
        # \\z[Название]\n{Текст}{...} — перенос строки между аргументами
        # обрывал чтение после первого, statement/subpoints терялись молча.
        text = (
            '\\begin{document}\n'
            '\\z[Парадокс сбережений]\n'
            '{Экономики многих стран характеризуются высоким долгом.}\n'
            '{\n'
            '\\n Найдите равновесный уровень выпуска.\n'
            '}\n'
            '\\end{document}'
        )
        blocks, warnings = parse_z_blocks(text)
        self.assertEqual(warnings, [])
        parsed = interpret_z_args(blocks[0])
        self.assertEqual(parsed['name'], 'Парадокс сбережений')
        self.assertIn('высоким долгом', parsed['statement'])
        self.assertEqual(len(parsed['subpoints']), 1)

    def test_real_file_fiscal_policy_first_problem(self):
        # Живой пример — Подборки/Макроэкономика/Фискальная политика.tex,
        # первая задача (см. materials/corpus_sources/lesh_2026_gamma).
        text = (
            '\\begin{document}\n'
            '\\z[Остров Мадагаскар]{В закрытой экономике острова Мадагаскар '
            'потребление зависит от располагаемого\nдохода следующим образом: '
            '$C = 10 + 0,75Y_d$, где $Y_d$ - располагаемый доход\n'
            'домохозяйств.}{\n'
            '\\n Определите ВВП острова Мадагаскар\n'
            '\\n Как изменится ВВП острова Мадагаскар, если государственные '
            'закупки вырастут на\n10?}\n'
            '\\end{document}'
        )
        blocks, warnings = parse_z_blocks(text)
        self.assertEqual(warnings, [])
        parsed = interpret_z_args(blocks[0])
        self.assertEqual(parsed['name'], 'Остров Мадагаскар')
        self.assertIn('потребление зависит', parsed['statement'])
        self.assertEqual(len(parsed['subpoints']), 2)
        self.assertIn('Определите ВВП острова Мадагаскар', parsed['subpoints'][0])


class InterpretZArgsTests(SimpleTestCase):
    def test_all_five_positions_full_form(self):
        # \\z[Название][20 баллов]{Текст}{\\n Пункт;}[Источник]
        args = [
            ('[', 'Название'),
            ('[', '20 баллов'),
            ('{', 'Текст'),
            ('{', '\\n Пункт;'),
            ('[', 'Источник'),
        ]
        parsed = interpret_z_args(args)
        self.assertEqual(parsed['name'], 'Название')
        self.assertEqual(parsed['points'], '20 баллов')
        self.assertEqual(parsed['statement'], 'Текст')
        self.assertEqual(parsed['subpoints'], ['Пункт'])
        self.assertEqual(parsed['source'], 'Источник')

    def test_minimal_form_statement_only(self):
        # \\z{Текст} — задача без пунктов и дополнительных сведений.
        args = [('{', 'Текст без пунктов.')]
        parsed = interpret_z_args(args)
        self.assertIsNone(parsed['name'])
        self.assertIsNone(parsed['points'])
        self.assertEqual(parsed['statement'], 'Текст без пунктов.')
        self.assertEqual(parsed['subpoints'], [])
        self.assertIsNone(parsed['source'])

    def test_empty_args_gives_empty_statement(self):
        parsed = interpret_z_args([])
        self.assertEqual(parsed['statement'], '')
        self.assertEqual(parsed['subpoints'], [])
