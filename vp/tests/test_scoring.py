"""Тесты правил подсчёта баллов ВП (vp/scoring.py).

Задания здесь — несохранённые `VPItem`: подсчёт от базы не зависит.
"""
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from vp.models import VPItem
from vp.scoring import normalize_short, score_attempt, score_item
from vp.tests.helpers import answer_all, make_full_variant

D = Decimal


def short(answer, points='2', **kw):
    return VPItem(kind='short_text', answer=answer, points=D(points), **kw)


def single(correct, points='4', **kw):
    options = [{'n': n, 'text': str(n)} for n in range(1, 6)]
    return VPItem(kind='single', options=options, correct=correct,
                  points=D(points), **kw)


def multi(correct, penalty=True, points='3'):
    options = [{'n': n, 'text': str(n)} for n in range(1, 6)]
    return VPItem(kind='multi', options=options, correct=correct,
                  points=D(points), penalty=penalty)


def match(correct, points='3'):
    return VPItem(kind='match', correct=correct, points=D(points))


class ShortTextTests(SimpleTestCase):
    def test_01_case_insensitive(self):
        self.assertEqual(score_item(short('лоренца'), 'Лоренца'), (D('2.00'), True))

    def test_02_spaces_collapsed(self):
        item = short('кривая лоренца')
        self.assertEqual(score_item(item, '  Кривая   Лоренца '), (D('2.00'), True))

    def test_03_yo_equals_ye(self):
        self.assertEqual(score_item(short('емкость'), 'ёмкость'), (D('2.00'), True))

    def test_04_blank_is_zero_and_wrong(self):
        self.assertEqual(score_item(short('лоренца'), ''), (D('0.00'), False))
        self.assertEqual(score_item(short('лоренца'), None), (D('0.00'), False))

    def test_05_wrong_penalty(self):
        item = short('лоренца', wrong_penalty=D('1'))
        self.assertEqual(score_item(item, 'кейнса'), (D('-1.00'), False))

    def test_accepted_synonym_and_trailing_dot(self):
        item = short('паритет', accepted=['ппс'])
        self.assertEqual(score_item(item, 'ППС.'), (D('2.00'), True))

    def test_hyphen_is_not_touched(self):
        self.assertEqual(normalize_short('Пяти-летка'), 'пяти-летка')
        self.assertNotEqual(normalize_short('пятилетка'), normalize_short('пяти-летка'))


class SingleTests(SimpleTestCase):
    def test_06_right_and_wrong(self):
        item = single([3])
        self.assertEqual(score_item(item, 3), (D('4.00'), True))
        self.assertEqual(score_item(item, 2), (D('0.00'), False))


class MultiTests(SimpleTestCase):
    def check(self, marked, expected, **kw):
        item = multi([1, 3], **kw)
        self.assertEqual(score_item(item, marked)[0], D(expected), marked)

    def test_07_penalty_cases(self):
        self.check([1, 3], '3.00')
        self.check([1], '1.50')
        self.check([1, 3, 2], '2.00')
        self.check([1, 2, 3, 4, 5], '0.00')
        self.check([2, 4], '0.00')  # −2,00 до клэмпа
        self.check([], '0.00')

    def test_07_full_marks_is_correct(self):
        self.assertEqual(score_item(multi([1, 3]), [1, 3]), (D('3.00'), True))
        self.assertFalse(score_item(multi([1, 3]), [1])[1])

    def test_08_no_penalty_flag(self):
        self.check([1, 2], '1.50', penalty=False)


class MatchTests(SimpleTestCase):
    def test_09_three_of_four(self):
        item = match({'а': 3, 'б': 1, 'в': 2, 'г': 4})
        raw = {'а': 3, 'б': 1, 'в': 2, 'г': 5}
        self.assertEqual(score_item(item, raw), (D('2.25'), False))

    def test_09b_rounding_is_half_up(self):
        # Точное значение 0,125 — ровно половина копейки: HALF_UP даёт 0,13,
        # ROUND_DOWN дал бы 0,12. Пример 9 (2,25) округления не проверяет.
        item = match({'а': 1, 'б': 2, 'в': 3, 'г': 4}, points='0.5')
        self.assertEqual(score_item(item, {'а': 1})[0], D('0.13'))
        # И третья часть — не «красивая» дробь: 2 × 1/3 = 0,666… → 0,67.
        item = match({'а': 1, 'б': 2, 'в': 3}, points='2')
        self.assertEqual(score_item(item, {'а': 1})[0], D('0.67'))

    def test_no_penalty_ever(self):
        item = match({'а': 1, 'б': 2})
        self.assertEqual(score_item(item, {'а': 9, 'б': 9})[0], D('0.00'))


class AttemptTests(TestCase):
    def test_10_all_right_is_exactly_100(self):
        variant = make_full_variant()
        self.assertEqual(variant.items.count(), 44)
        self.assertEqual(score_attempt(answer_all(variant, right=True)), D('100.00'))

    def test_11_all_wrong_is_zero(self):
        variant = make_full_variant()
        self.assertEqual(score_attempt(answer_all(variant, right=False)), D('0.00'))
