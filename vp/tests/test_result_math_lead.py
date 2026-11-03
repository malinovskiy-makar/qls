"""Краткая подпись результата не оставляет сырой TeX от обрезанной формулы."""
from django.test import SimpleTestCase
import yaml
from pathlib import Path

from vp.review import _lead


class ResultMathLeadTests(SimpleTestCase):
    def test_real_demo_11_task_16_does_not_cut_consumption_formula(self):
        source = Path(__file__).resolve().parents[2] / 'data/vp/vp-2tur-2026-demo-11.yaml'
        data = yaml.safe_load(source.read_text())
        item = next(item for item in data['items'] if item['n'] == 16)
        lead = _lead(item['statement'])
        self.assertEqual(lead, 'В закрытой экономике функция совокупного потребления домохозяйств имеет вид…')
        self.assertIn('$C = 200 + 0{,}6Y_d$', item['statement'])

    def test_cut_inside_any_supported_math_delimiter_keeps_it_whole(self):
        for left, right in (('$', '$'), ('$$', '$$'), (r'\(', r'\)'), (r'\[', r'\]')):
            with self.subTest(left=left):
                formula = left + 'x + ' * 30 + 'y' + right
                self.assertEqual(_lead('Условие ' + formula + ' продолжение'), 'Условие…')
                self.assertEqual(_lead(formula + ' продолжение'), formula + '…')

    def test_formula_before_cut_currency_and_short_text_are_preserved(self):
        self.assertEqual(_lead('Цена $P = 10$.'), 'Цена $P = 10$.')
        lead = _lead(r'Цена \$100; спрос $Q = 5$. ' + 'Дальше текст. ' * 20)
        self.assertTrue(lead.startswith(r'Цена \$100; спрос $Q = 5$.'))
        self.assertTrue(lead.endswith('…'))
