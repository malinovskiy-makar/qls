"""Сессия R, фаза 1: длинный минус, `canonical_number`, `nbsp_num`.

Длинный минус «−» и тире перед числом — 0 баллов, как раньше, но в разборе это своя
причина `minus` (решение владельца 28.10.2026). `canonical_number` — одна функция «как
правильно записать это число»; на ней же живёт мягкая починка `would_be_correct`.
"""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from vp import review
from vp.models import VPAttempt, VPItem
from vp.scoring import canonical_number, explain_item, score_item
from vp.templatetags.vp_extras import nbsp_num
from vp.tests.helpers import load_demo

User = get_user_model()
NBSP = ' '

# (эталон, ответ, балл из 5, format_error, would_be_correct, number_fix)
TABLE = [
    ('-318', '−318', '0', 'minus', True, '-318'),
    ('-318', '–318', '0', 'minus', True, '-318'),
    ('-0,12', '−0,12', '0', 'minus', True, '-0,12'),
    ('-318', '−25 000', '0', 'minus', False, ''),
    ('-318', '-318', '5', None, None, ''),
    ('25000', '25 000', '0', 'space', True, '25000'),
    ('37,5', '37.5', '0', 'dot', True, '37,5'),
    ('37,5', '37.5.1', '0', 'dot', False, ''),
]

CANONICAL = [
    ('37.5', '37,5'), ('25 000', '25000'), ('20%', '20'), ('−0,12', '-0,12'),
    ('1,607', '1,61'), ('3,125', '3,13'), ('−0,125', '-0,13'),
    ('1 200,50 ₽', '1200,50'), ('7¼', None), (',5', None), ('абв', None),
]


def number_item(answer, points='5'):
    return VPItem(kind='number', block='number', number=5, statement='…',
                  answer=answer, accepted=[], points=Decimal(points))


class LongMinusTableTests(SimpleTestCase):
    def test_table(self):
        for answer, given, score, error, would, fix in TABLE:
            with self.subTest(answer=answer, given=given):
                item = number_item(answer)
                got, _ = score_item(item, given)
                self.assertEqual(got, Decimal(score).quantize(Decimal('0.01')))
                explain = explain_item(item, given)
                self.assertEqual(explain['format_error'], error)
                self.assertEqual(explain['would_be_correct'], would)
                self.assertEqual(review._number_fix(explain), fix)

    def test_every_long_minus_sign_is_minus(self):
        for sign in '−‒–—﹣－':
            with self.subTest(sign=hex(ord(sign))):
                self.assertEqual(explain_item(number_item('-5'), sign + '5')['format_error'],
                                 'minus')
                self.assertTrue(explain_item(number_item('-5'), sign + '5')['would_be_correct'])


class CanonicalNumberTests(SimpleTestCase):
    def test_table(self):
        for text, expected in CANONICAL:
            with self.subTest(text=text):
                self.assertEqual(canonical_number(text), expected)


class NbspNumTests(SimpleTestCase):
    def test_digit_groups_only_outside_formulas(self):
        self.assertEqual(nbsp_num('20 000 рублей'), f'20{NBSP}000 рублей')
        self.assertEqual(nbsp_num('1 000 000').count(NBSP), 2)
        self.assertEqual(nbsp_num('$x = 20 000$'), '$x = 20 000$')
        self.assertEqual(nbsp_num('в 1 из 5'), 'в 1 из 5')
        self.assertEqual(nbsp_num(r'\(1 000\) и 2 000'), rf'\(1 000\) и 2{NBSP}000')


class LongMinusReviewLineTests(TestCase):
    """Строка разбора «длинный минус» — владельцу; у чужого её нет."""

    def setUp(self):
        self.variant = load_demo('10')
        item = self.variant.items.get(number=7)
        item.answer = '-318'
        item.save()
        self.owner = Client()
        self.owner.force_login(User.objects.create_user('vp_minus', password='p12345'))
        self.owner.post(reverse('vp:start', args=[self.variant.slug]))
        attempt = VPAttempt.objects.get(variant=self.variant)
        self.owner.post(reverse('vp:save', args=[attempt.public_code]),
                        json.dumps({'answers': [{'item': 7, 'raw': '−318'}]}),
                        content_type='application/json')
        self.owner.post(reverse('vp:finish', args=[attempt.public_code]))
        self.url = reverse('vp:result', args=[attempt.public_code])

    def test_owner_sees_long_minus_reason_and_fix(self):
        html = self.owner.get(self.url).content.decode()
        self.assertIn('длинный минус «−» или тире вместо обычного «-».', html)
        self.assertIn('Нужно «-318», а не «−318».', html)

    def test_stranger_does_not(self):
        stranger = Client()
        stranger.force_login(User.objects.create_user('vp_minus2', password='p12345'))
        html = stranger.get(self.url).content.decode()
        self.assertNotIn('длинный минус', html)
        self.assertNotIn('Нужно «-318»', html)
