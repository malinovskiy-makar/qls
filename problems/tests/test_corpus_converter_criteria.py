from django.test import SimpleTestCase

from problems.corpus_converter.criteria import parse_shkolkovo_criteria


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
