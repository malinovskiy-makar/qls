"""Прохождение варианта 2 тура: страница, автосохранение новых видов, сдача.

Варианты — настоящие демоверсии ВШЭ из `data/vp/` (через `helpers.load_demo`).
"""
import json
import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp import views
from vp.blocks import NUMBER_RULE
from vp.models import VPAnswer, VPAttempt, VPItem
from vp.tests.helpers import load_demo, perfect_raw

User = get_user_model()


class Tour2Base(TestCase):
    band = '10'

    def setUp(self):
        self.variant = load_demo(self.band)
        self.client = Client()
        self.client.force_login(User.objects.create_user('vp_t2', password='p12345'))

    def start(self, variant=None, **post):
        variant = variant or self.variant
        self.client.post(reverse('vp:start', args=[variant.slug]), post)
        return VPAttempt.objects.filter(variant=variant).order_by('-id').first()

    def html(self, attempt):
        response = self.client.get(reverse('vp:take', args=[attempt.public_code]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def payload(self, html):
        """Что страница несёт про задания: форма и `vp-config`. Общие стили и скрипты
        сайта (там числа вроде «160» и слово «змейка» в комментариях) — не в счёт."""
        form = html.split('id="vp-form"', 1)[1].split('</form>', 1)[0]
        config = html.split('id="vp-config"', 1)[1].split('</script>', 1)[0]
        return form + config

    def save(self, attempt, answers):
        return self.client.post(reverse('vp:save', args=[attempt.public_code]),
                                json.dumps({'answers': answers}),
                                content_type='application/json')


class Tour2PageTests(Tour2Base):
    def test_page_renders_all_items_and_new_kinds(self):
        html = self.html(self.start())
        found = [int(n) for n in re.findall(r'<section class="vp-item" id="vp-item-(\d+)"', html)]
        self.assertEqual(found, list(range(1, 19)))
        # Пропуски: 8 списков прямо в тексте, имена item-3.<k>.
        self.assertEqual(sorted(re.findall(r'name="item-3\.(\d+)"', html), key=int),
                         [str(k) for k in range(1, 9)])
        self.assertNotIn('[[', self.payload(html))
        # Соотнесение: 4 строки с текстами из `rows`.
        self.assertEqual(re.findall(r'name="item-4\.(\d+)"', html), ['1', '2', '3', '4'])
        self.assertIn('Прожиточный минимум может использоваться', html)
        # Число: текстовое поле с десятичной клавиатурой и подписью.
        self.assertRegex(html, r'name="item-5" type="text"[^>]*inputmode="decimal"')
        self.assertEqual(html.count('Только число: запятая, до сотых'), 14)

    def test_number_rule_stands_once_before_the_number_block(self):
        html = self.html(self.start())
        self.assertEqual(html.count(NUMBER_RULE), 1)
        self.assertLess(html.index(NUMBER_RULE), html.index('id="vp-item-5"'))
        self.assertGreater(html.index(NUMBER_RULE), html.index('id="vp-item-4"'))

    def test_group_frame_around_17_and_18(self):
        html = self.html(self.start())
        self.assertEqual(html.count('class="vp-group"'), 1)
        frame = html.split('class="vp-group"', 1)[1]
        self.assertIn('Задачи 17–18 – общее условие', frame)
        self.assertLess(frame.index('id="vp-item-17"'), frame.index('id="vp-item-18"'))

    def test_no_snake_hints(self):
        html = self.html(self.start())
        config = json.loads(re.search(
            r'<script id="vp-config" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(config['textNumbers'], [])
        self.assertNotIn('змейк', self.payload(html).lower())

    def test_take_hides_answers(self):
        """Ни одного эталона демоверсии 10 класса в HTML: числа, буквы соотнесения,
        выбранные слова пула («Джини» есть в пуле, но не выбрано)."""
        page = self.html(self.start())
        html = self.payload(page)
        visible = ' '.join(i.statement + ' '.join(o['text'] for o in i.options)
                           + ' '.join(i.rows) + i.table_html for i in self.variant.items.all())
        distinctive = [i.answer for i in self.variant.items.filter(kind='number')
                       if len(i.answer) >= 3 and i.answer not in visible]
        self.assertIn('25000', distinctive)
        for secret in distinctive:
            self.assertNotIn(secret, html)
        self.assertIn('Джини', html)
        self.assertNotIn(' selected', html)
        self.assertNotIn('БАББ', html)
        for leak in ('"correct"', 'accepted', 'data-answer', 'data-correct'):
            self.assertNotIn(leak, page)
        for item in self.variant.items.exclude(solution=''):
            self.assertNotIn(item.solution, page)

    def test_rows_carry_only_safe_fields(self):
        for number in (3, 4, 5, 17):
            row = views._row(self.variant.items.get(number=number), None)
            for forbidden in ('answer', 'correct', 'accepted', 'solution'):
                self.assertNotIn(forbidden, row)
            self.assertFalse(any(isinstance(v, VPItem) for v in row.values()))


class Tour2SaveTests(Tour2Base):
    def test_save_and_read_back_number_gaps_and_matching(self):
        attempt = self.start()
        response = self.save(attempt, [
            {'item': 5, 'raw': ' 25000 '},
            {'item': 9, 'raw': '98.0'},
            {'item': 3, 'raw': {'1': 14, '4': 2}},
            {'item': 4, 'raw': {'1': 2, '2': 1}},
        ])
        self.assertEqual(response.status_code, 200, response.content)
        raw = {a.item.number: a.raw for a in VPAnswer.objects.filter(attempt=attempt)}
        self.assertEqual(raw, {5: '25000', 9: '98.0', 3: {'1': 14, '4': 2},
                               4: {'1': 2, '2': 1}})
        html = self.html(attempt)
        self.assertRegex(html, r'name="item-5" type="text"\s+value="25000"')
        self.assertRegex(html, r'name="item-9" type="text"\s+value="98.0"')
        block3 = html.split('id="vp-item-3"', 1)[1].split('</section>', 1)[0]
        self.assertEqual(len(re.findall(r' selected', block3)), 2)
        self.assertRegex(block3, r'<option value="14" selected>развитый</option>')

    def test_number_must_be_a_string(self):
        response = self.save(self.start(), [{'item': 5, 'raw': 25000}])
        self.assertEqual(response.status_code, 400)

    def test_gap_key_must_exist(self):
        response = self.save(self.start(), [{'item': 3, 'raw': {'9': 1}}])
        self.assertEqual(response.status_code, 400)


class Tour2FinishTests(TestCase):
    """Числовой инвариант: идеальные ответы → 100,00; пустая сдача → 0,00."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(User.objects.create_user('vp_t2f', password='p12345'))

    def run_attempt(self, variant, perfect):
        self.client.post(reverse('vp:start', args=[variant.slug]))
        attempt = VPAttempt.objects.filter(variant=variant).order_by('-id').first()
        if perfect:
            answers = [{'item': i.number, 'raw': perfect_raw(i)} for i in variant.items.all()]
            response = self.client.post(reverse('vp:save', args=[attempt.public_code]),
                                        json.dumps({'answers': answers}),
                                        content_type='application/json')
            self.assertEqual(response.status_code, 200, response.content)
        self.client.post(reverse('vp:finish', args=[attempt.public_code]))
        attempt.refresh_from_db()
        return attempt

    def test_perfect_and_empty(self):
        for band in ('9', '10', '11'):
            with self.subTest(band=band):
                variant = load_demo(band)
                full = self.run_attempt(variant, perfect=True)
                self.assertEqual((full.score, full.max_score), (Decimal('100.00'), Decimal('100.00')))
                empty = self.run_attempt(variant, perfect=False)
                self.assertEqual(empty.score, Decimal('0.00'))

    def test_form_fields_are_read_on_finish(self):
        """Последняя порция из формы сдачи: число и пропуски доходят и без автосохранения."""
        variant = load_demo('10')
        self.client.post(reverse('vp:start', args=[variant.slug]))
        attempt = VPAttempt.objects.get(variant=variant)
        self.client.post(reverse('vp:finish', args=[attempt.public_code]),
                         {'item-5': '25000', 'item-3.1': '14', 'item-4.1': '2'})
        raw = {a.item.number: a.raw for a in attempt.answers.all() if a.raw is not None}
        self.assertEqual(raw, {5: '25000', 3: {'1': 14}, 4: {'1': 2}})
        attempt.refresh_from_db()
        # 5 (число) + 9 × 1/8 (пропуск) + 9 × 1/4 (соотнесение) = 5 + 1,125 + 2,25.
        self.assertEqual(attempt.score, Decimal('8.38'))
