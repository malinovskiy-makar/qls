"""Задание с вводом числа (2 тур): правило ВШЭ и решения владельца от 24.10.2026.

Неверный формат — 0 баллов, как у ВШЭ; разбор называет причину и говорит, было ли
само число верным. Лишние нули после запятой засчитываются: «37,50» = «37,5».
Таблица — из задания сессии, значения обязательны все.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from vp.models import VPItem
from vp.scoring import explain_item, score_item

# (эталон, accepted, ответ, балл из 5, format_error, would_be_correct)
TABLE = [
    ('37,5', [], '37,5', '5', None, None),
    ('37,5', [], '37,50', '5', None, None),
    ('37,5', [], ' 37,5 ', '5', None, None),
    ('37,5', [], '37.5', '0', 'dot', True),
    ('37,5', [], '37,49', '0', None, None),
    ('37,5', [], '3 7,5', '0', 'space', True),
    ('25000', [], '25 000', '0', 'space', True),
    ('25000', [], '25000 руб', '0', 'units', True),
    ('25000', [], '25000₽', '0', 'units', True),
    ('-318', [], '-318', '5', None, None),
    ('-318', [], '- 318', '0', 'space', True),
    ('-318', [], '318', '0', None, None),
    ('3,13', ['3,125'], '3,125', '5', None, None),
    ('3,13', ['3,125'], '3,13', '5', None, None),
    ('3,13', ['3,125'], '3,126', '0', 'decimals', True),
    ('1,61', [], '1,607', '0', 'decimals', True),
    ('1,61', [], '1,6', '0', None, None),
    ('2930,5', [], '2930,50', '5', None, None),
    ('20', [], '20%', '0', 'units', True),
]


def number_item(answer, accepted=(), points='5'):
    return VPItem(kind='number', block='number', number=5, statement='…',
                  answer=answer, accepted=list(accepted), points=Decimal(points))


class NumberScoringTableTests(SimpleTestCase):
    def test_table(self):
        for answer, accepted, given, score, error, would in TABLE:
            with self.subTest(answer=answer, given=given):
                item = number_item(answer, accepted)
                got, is_correct = score_item(item, given)
                self.assertEqual(got, Decimal(score).quantize(Decimal('0.01')))
                self.assertIs(is_correct, score == '5')
                explain = explain_item(item, given)
                self.assertEqual(explain['kind'], 'number')
                self.assertEqual(explain['format_error'], error)
                self.assertEqual(explain['would_be_correct'], would)
                self.assertEqual(explain['given'], given.strip())

    def test_blank_is_not_answered(self):
        for blank in ('', '   ', None):
            with self.subTest(blank=blank):
                self.assertEqual(score_item(number_item('20'), blank), (Decimal('0.00'), None))
                self.assertEqual(explain_item(number_item('20'), blank)['kind'], 'blank')

    def test_points_come_from_item(self):
        """У 9 класса задание с числом стоит 6 баллов: балл — из данных задания."""
        item = number_item('37,5', points='6')
        self.assertEqual(score_item(item, '37,50'), (Decimal('6.00'), True))
        self.assertEqual(score_item(item, '37.5'), (Decimal('0.00'), False))
        self.assertEqual(explain_item(item, '37.5')['points'], Decimal('6.00'))

    def test_accepted_match_is_flagged(self):
        explain = explain_item(number_item('3,13', ['3,125']), '3,125')
        self.assertTrue(explain['accepted_match'])
        self.assertIsNone(explain['format_error'])

    def test_explain_never_carries_the_answer(self):
        """Эталон в структуру кладёт только экран владельца, не `explain_item`."""
        explain = explain_item(number_item('37,5'), '37.5')
        self.assertNotIn('37,5', [str(v) for v in explain.values()])
        self.assertNotIn('answer', explain)

    def test_other_format_errors(self):
        for given in (',5', '5,', '1,2,3', '--5'):
            with self.subTest(given=given):
                explain = explain_item(number_item('5'), given)
                self.assertEqual(explain['format_error'], 'other')
                self.assertEqual(explain['score'], Decimal('0.00'))

    def test_wrong_value_with_bad_format_is_not_correct(self):
        explain = explain_item(number_item('37,5'), '38.5')
        self.assertEqual((explain['format_error'], explain['would_be_correct']), ('dot', False))

    def test_trailing_newline_is_a_format_error_free_edge(self):
        """Перевод строки по краю срезается, как пробел; внутри — ошибка «пробел»."""
        self.assertEqual(score_item(number_item('37,5'), '37,5\n'), (Decimal('5.00'), True))
        self.assertEqual(explain_item(number_item('37,5'), '37\n,5')['format_error'], 'space')
