"""Сессия R, фаза 4: тексты и общие подписи.

Фраза диапазонов («В заданиях 3 и 4», а не «В задании 3–4»), «Мои попытки» без змейки и с
«архивом» у скрытого тура, строка меты варианта одной функцией, класс не повторяется.
"""
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from vp import blocks
from vp.models import VPAttempt
from vp.tests.helpers import load_demo, make_published

User = get_user_model()


def section(first, last):
    return {'first': first, 'last': last}


class InTasksPhraseTests(SimpleTestCase):
    def test_words_and_pairs(self):
        self.assertEqual(blocks.in_tasks([section(3, 3), section(4, 4)]), 'В заданиях 3 и 4')
        self.assertEqual(blocks.in_tasks([section(1, 3)]), 'В заданиях 1–3')
        self.assertEqual(blocks.in_tasks([section(4, 4)]), 'В задании 4')
        self.assertEqual(blocks.in_tasks([section(5, 18)]), 'В заданиях 5–18')
        self.assertEqual(blocks.in_tasks([section(1, 35), section(43, 44)]),
                         'В заданиях 1–35 и 43–44')
        self.assertEqual(blocks.in_tasks([]), '')


class TextsTests(TestCase):
    def setUp(self):
        for band in ('9', '10', '11'):
            load_demo(band)
        self.client = Client()
        self.user = User.objects.create_user('vp_txt', password='p12345')
        self.client.force_login(self.user)

    def rules(self):
        html = self.client.get(reverse('vp:index')).content.decode()
        return html.split('<dialog class="vp-rules"', 1)[1].split('</dialog>', 1)[0]

    def test_rules_dialog_phrases(self):
        rules = self.rules()
        self.assertEqual(rules.count('0 баллов, как на туре'), 1)
        score = rules.split('id="vp-r-score"', 1)[1].split('</section>', 1)[0]
        self.assertIn('0 баллов, как на туре', score)
        number = rules.split('id="vp-r-number"', 1)[1].split('</section>', 1)[0]
        self.assertNotIn('0 баллов, как на туре', number)
        ninth, tenth = score.split('10 класс и 11 класс', 1)
        self.assertIn('В заданиях 1 и 2', tenth)
        self.assertIn('В заданиях 3 и 4', tenth)
        self.assertIn('В заданиях 1–3', ninth)
        self.assertIn('В заданиях 4 и 5', ninth)
        self.assertNotIn('задании 3–4', rules)

    def test_my_attempts_has_no_snake_and_marks_the_archive(self):
        old = make_published('vp-t1')            # вариант 1 тура: тур скрыт
        VPAttempt.objects.create(
            variant=old, user=self.user, public_code='r-arch-1', with_timer=True,
            is_ranked=True, max_score=old.max_score, score=Decimal('10'),
            expires_at=timezone.now() + timedelta(minutes=30), submitted_at=timezone.now())
        html = self.client.get(reverse('vp:my')).content.decode()
        html = html.split('class="vp-my"', 1)[1]        # сама страница, без стилей и шапки
        self.assertNotIn('змейк', html.lower())
        row = html[html.index('1 тур'):html.index('r-arch-1')]   # от метки тура до ссылки «Разбор»
        self.assertIn('архив', row)
        self.assertNotIn('в таблице', row)

    def test_card_meta_and_band_once_on_result(self):
        html = self.client.get(reverse('vp:variants') + '?band=10').content.decode()
        # R-fix: происхождение уже в надзаголовке карточки — в мете его нет.
        self.assertIn('<p class="vp-vcard-m">2026/27 · 18 заданий · 70 мин</p>', html)
        variant = load_demo('10')
        self.client.post(reverse('vp:start', args=[variant.slug]))
        attempt = VPAttempt.objects.get(variant=variant)
        self.client.post(reverse('vp:save', args=[attempt.public_code]),
                         json.dumps({'answers': [{'item': 5, 'raw': '1'}]}),
                         content_type='application/json')
        self.client.post(reverse('vp:finish', args=[attempt.public_code]))
        result = self.client.get(reverse('vp:result', args=[attempt.public_code])).content.decode()
        head = result.split('<h1', 1)[1].split('</h1>', 1)[0]
        self.assertEqual(head.count('10 класс'), 1)
