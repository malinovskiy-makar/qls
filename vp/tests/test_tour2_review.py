"""Разбор и «Дорешать вне зачёта» для 2 тура: число, пропуски, соотнесение.

Владельцу — откуда балл и почему 0 за формат; чужому — ни эталона, ни этих строк.
"""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp import review
from vp.models import VPAnswer, VPAttempt
from vp.tests.helpers import load_demo

User = get_user_model()

GAPS_6_OF_8 = {'1': 14, '2': 12, '3': 3, '4': 2, '5': 6, '6': 16, '7': 1, '8': 2}


class Tour2ReviewTests(TestCase):
    def setUp(self):
        self.variant = load_demo('10')
        item = self.variant.items.get(number=6)
        item.answer = '37,5'          # эталон из примера владельца
        item.save()
        self.owner = Client()
        self.owner.force_login(User.objects.create_user('vp_rev', password='p12345'))
        self.stranger = Client()
        self.stranger.force_login(User.objects.create_user('vp_rev2', password='p12345'))
        self.owner.post(reverse('vp:start', args=[self.variant.slug]))
        self.attempt = VPAttempt.objects.get(variant=self.variant)
        answers = [
            {'item': 6, 'raw': '37.5'},
            {'item': 17, 'raw': '1,607'},
            {'item': 5, 'raw': '25000'},
            {'item': 9, 'raw': '25 000'},
            {'item': 3, 'raw': GAPS_6_OF_8},
            {'item': 4, 'raw': {'1': 2, '2': 1, '3': 1}},
        ]
        self.owner.post(reverse('vp:save', args=[self.attempt.public_code]),
                        json.dumps({'answers': answers}), content_type='application/json')
        self.owner.post(reverse('vp:finish', args=[self.attempt.public_code]))
        self.url = reverse('vp:result', args=[self.attempt.public_code])

    def card(self, html, number):
        return html.split(f'id="vp-r-{number}"', 1)[1].split('</article>', 1)[0]

    def test_owner_sees_format_reason_and_true_number(self):
        html = self.owner.get(self.url).content.decode()
        six = self.card(html, 6)
        self.assertIn('0 из 5: точка вместо запятой. Нужно писать «37,5», а не «37.5».', six)
        self.assertIn('Само число верное: на туре этот ответ тоже получил бы 0 из-за формата.', six)
        self.assertIn('0 из 5: больше двух знаков после запятой. Ответ нужно округлить до сотых.',
                      self.card(html, 17))
        nine = self.card(html, 9)
        self.assertIn('пробел внутри числа. Нужно «25000», а не «25 000».', nine)
        self.assertIn('Число тоже неверное.', nine)      # эталон 98
        self.assertIn('5 из 5', self.card(html, 5))
        self.assertNotIn('точка вместо', self.card(html, 5))

    def test_owner_sees_share_line_for_gaps_and_matching(self):
        html = self.owner.get(self.url).content.decode()
        gaps = self.card(html, 3)
        self.assertIn('Верно 6 из 8.', gaps)
        self.assertIn('9 × 6/8 = 6,75', gaps)
        self.assertIn('верно: рента', gaps)              # №7: выбран «валютный курс»
        match = self.card(html, 4)
        self.assertIn('9 × 2/4 = 4,50', match)           # 1 и 2 верно, 3 неверно, 4 пусто
        self.assertIn('не выбрано', match)

    def test_points_of_9th_grade_come_from_data(self):
        variant = load_demo('9')
        client = Client()
        client.force_login(User.objects.create_user('vp_rev9', password='p12345'))
        client.post(reverse('vp:start', args=[variant.slug]))
        attempt = VPAttempt.objects.get(variant=variant)
        number = variant.items.filter(kind='number').first()
        client.post(reverse('vp:save', args=[attempt.public_code]),
                    json.dumps({'answers': [{'item': number.number, 'raw': number.answer + '.0'}]}),
                    content_type='application/json')
        client.post(reverse('vp:finish', args=[attempt.public_code]))
        html = client.get(reverse('vp:result', args=[attempt.public_code])).content.decode()
        self.assertIn('0 из 6: точка вместо запятой.', self.card(html, number.number))

    def test_no_snake_section(self):
        html = self.owner.get(self.url).content.decode()
        self.assertEqual(review.chain_review(self.attempt), [])
        self.assertNotIn('id="vp-chain"', html)
        self.assertIn('id="vp-tests"', html)

    def test_stranger_sees_neither_answer_nor_reason(self):
        html = self.stranger.get(self.url).content.decode()
        self.assertEqual(self.stranger.get(self.url).status_code, 200)
        for secret in ('37,5', 'точка вместо запятой', 'Само число верное', 'Число тоже неверное',
                       '× 6/8 = 6,75', 'id="vp-tests"', 'рента'):
            self.assertNotIn(secret, html)

    def test_unanswered_item_has_no_answer_but_practice(self):
        html = self.owner.get(self.url).content.decode()
        ten = self.card(html, 10)
        self.assertIn('Не отвечено', ten)
        self.assertIn('data-kind="number"', ten)
        self.assertNotIn('840', ten)
        self.assertNotIn('Верный ответ', ten)
        row = next(r for r in review.tests_review(self.attempt) if r['number'] == 10)
        self.assertEqual((row['right'], row['solution'], row['explain']), ('', '', None))


class Tour2PracticeTests(TestCase):
    def setUp(self):
        self.variant = load_demo('10')
        self.client = Client()
        self.client.force_login(User.objects.create_user('vp_pr', password='p12345'))
        self.client.post(reverse('vp:start', args=[self.variant.slug]))
        self.attempt = VPAttempt.objects.get(variant=self.variant)
        self.client.post(reverse('vp:finish', args=[self.attempt.public_code]))
        self.url = reverse('vp:practice', args=[self.attempt.public_code])

    def check(self, number, raw):
        response = self.client.post(self.url, json.dumps({'item': number, 'raw': raw}),
                                    content_type='application/json')
        return response.status_code, response.json()

    def test_number_gaps_and_matching_by_the_same_rules(self):
        before = list(VPAnswer.objects.values_list('id', 'raw', 'score'))
        self.assertEqual(self.check(5, '25000'), (200, {'is_correct': True, 'right': '25000'}))
        self.assertEqual(self.check(5, '25 000'), (200, {'is_correct': False, 'right': '25000'}))
        self.assertEqual(self.check(17, '1,610')[1]['is_correct'], False)   # три знака
        self.assertEqual(self.check(17, '1,61')[1]['is_correct'], True)
        status, data = self.check(4, {'1': 2, '2': 1, '3': 2, '4': 2})
        self.assertEqual((status, data['is_correct']), (200, True))
        self.assertIn('Прожиточный минимум может использоваться как граница для оценки '
                      'бедности.: А – абсолютная бедность', data['right'])
        status, data = self.check(3, {'1': 14})
        self.assertEqual((status, data['is_correct']), (200, False))
        self.assertTrue(data['right'].startswith('Пропуск 1: развитый; Пропуск 2: рабочая сила'))
        # «Дорешать» ничего не пишет.
        self.assertEqual(list(VPAnswer.objects.values_list('id', 'raw', 'score')), before)
