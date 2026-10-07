"""Экзамен для ИИ: разбор чисел, поиск чисел в тексте, ключи, сравнение.

Таблицы ниже — обязательный минимум из постановки сессии «Экзамен A»;
каждая строка — отдельный subTest, чтобы падение называло строку.
"""
from fractions import Fraction

from django.test import SimpleTestCase

from problems.ai_exam.numbers import (
    find_numbers, matches, parse_tol, propose_key, to_number,
)

MATCHES = [
    # (given, value, percent, tol, ожидание)
    ('12.1', '12', False, None, True),
    ('12.4', '12', False, None, False),
    ('1.2222', '1.2', False, None, True),
    ('1.26', '1.2', False, None, False),
    ('−1,2222', '-1.22', False, None, True),
    ('0,2549', '0.25', False, None, True),
    ('0.26', '0.25', False, None, False),
    ('0.3333', '1/3', False, None, True),
    ('0.3', '1/3', False, None, False),
    ('1250', '1 250', False, None, True),
    ('1005', '1000', False, None, True),
    ('1011', '1000', False, None, False),
    ('0.25', '25', True, None, True),
    ('25%', '25', True, None, True),
    ('0,3', '25', True, None, False),
    ('25%', '0.25', False, None, True),
    ('двадцать', '20', False, None, False),
    ('', '20', False, None, False),
    ('20 ед.', '20', False, None, True),
    ('\\frac{1}{3}', '1/3', False, None, True),
    ('$12{,}5$', '12.5', False, None, True),
    ('10.4', '10', False, '0.5', True),
    ('10.6', '10', False, '0.5', False),
]

PROPOSE = [
    # (сырой ответ, вид, число, единицы, проценты)
    ('20', 'exact', Fraction(20), '', False),
    ('12,5', 'exact', Fraction(25, 2), '', False),
    ('$-1{,}22$', 'exact', Fraction(-122, 100), '', False),
    ('25%', 'exact', Fraction(25), '', True),
    ('20 ед.', 'exact', Fraction(20), 'ед.', False),
    ('1 250 руб.', 'exact', Fraction(1250), 'руб.', False),
    ('\\frac{1}{3}', 'exact', Fraction(1, 3), '', False),
    ('Q = 20', 'extracted', Fraction(20), '', False),
    ('Q_1 = 30', 'extracted', Fraction(30), '', False),
    ('E ≈ −1,22 (по модулю больше 1) — спрос эластичен', 'none', None, '', False),
    ('P = 5, Q = 20', 'none', None, '', False),
    ('вырастет', 'none', None, '', False),
    ('', 'none', None, '', False),
    ('10^3', 'none', None, '', False),
]


class MatchesTests(SimpleTestCase):
    def test_table(self):
        for given, value, percent, tol, expected in MATCHES:
            with self.subTest(given=given, value=value, percent=percent, tol=tol):
                self.assertIs(matches(given, value, percent=percent, tol=tol),
                              expected)

    def test_key_not_a_number_never_matches(self):
        self.assertFalse(matches('20', 'вырастет'))

    def test_bad_tolerance_is_an_error_not_a_silent_default(self):
        for tol in ('-1', '0', 'много'):
            with self.subTest(tol=tol), self.assertRaises(ValueError):
                matches('10', '10', tol=tol)


class ProposeKeyTests(SimpleTestCase):
    def test_table(self):
        for raw, kind, number, unit, percent in PROPOSE:
            with self.subTest(raw=raw):
                key = propose_key(raw)
                self.assertEqual(key['kind'], kind)
                self.assertEqual(to_number(key['value']), number)
                self.assertEqual(key['unit'], unit)
                self.assertIs(key['percent'], percent)

    def test_value_is_written_with_a_dot(self):
        self.assertEqual(propose_key('12,5')['value'], '12.5')
        self.assertEqual(propose_key('$-1{,}22$')['value'], '-1.22')
        self.assertEqual(propose_key('1 250 руб.')['value'], '1250')
        self.assertEqual(propose_key('\\frac{1}{3}')['value'], '1/3')


class ToNumberTests(SimpleTestCase):
    def test_cleanup(self):
        cases = [
            ('$$7$$', Fraction(7)),
            ('≈ 3,5', Fraction(7, 2)),
            ('= 4.', Fraction(4)),
            ('1 250 000', Fraction(1250000)),
            ('\\dfrac{2}{5}', Fraction(2, 5)),
            ('–3', Fraction(-3)),
            ('12\\%', Fraction(12)),
            ('5 тыс. руб.', Fraction(5)),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(to_number(text), expected)

    def test_not_a_number(self):
        for text in ('', None, '12 5', '2·10^3', '10^3', 'Q = 20',
                     '5 очень длинных единиц'):
            with self.subTest(text=text):
                self.assertIsNone(to_number(text))

    def test_parse_tol(self):
        self.assertIsNone(parse_tol(''))
        self.assertIsNone(parse_tol(None))
        self.assertEqual(parse_tol('0,5'), Fraction(1, 2))


class FindNumbersTests(SimpleTestCase):
    def test_indices_and_powers_are_not_numbers(self):
        cases = [
            ('Q_1 = 30', [Fraction(30)]),
            ('Q_{1} = 30', [Fraction(30)]),
            ('x^2 + 4', [Fraction(4)]),
            ('P1 = 7', [Fraction(7)]),
            ('10^3', []),
            ('2·10^3 и ещё 5', [Fraction(5)]),
            ('$Q = 1{,}5$, $P = \\frac{1}{2}$', [Fraction(3, 2), Fraction(1, 2)]),
            ('E ≈ −1,22 (по модулю больше 1)', [Fraction(-122, 100), Fraction(1)]),
            ('ставка 25%', [Fraction(25)]),
            ('выручка 1 250 руб.', [Fraction(1250)]),
            ('ответ: вырастет', []),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(find_numbers(text), expected)
