"""Сессия R, фаза 7: змейка 1 тура в архиве (макет 03) — чипы слов и панели.

Старая попытка 1 тура открывается и владельцу, и чужому; владельцу — чипы по числу слов
змейки и определения, чужому — ни определения, ни эталона (данных у него нет вовсе).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from vp import views
from vp.models import VPAnswer, VPAttempt
from vp.tests.helpers import make_full_variant

User = get_user_model()
DEFINITION = 'Определение-проверка-цепочки'


class SnakeArchiveTests(TestCase):
    def setUp(self):
        self.variant = make_full_variant('vp-snake-archive')
        self.variant.is_published = True
        self.variant.save()
        first = self.variant.items.get(number=1)
        first.statement = DEFINITION
        first.save()
        self.user = User.objects.create_user('vp_snake', password='p12345')
        attempt = VPAttempt.objects.create(
            variant=self.variant, user=self.user, public_code=views._new_code(),
            with_timer=True, max_score=self.variant.max_score,
            expires_at=timezone.now() + timedelta(minutes=30))
        for item in self.variant.items.filter(number__in=(1, 2, 3)):
            VPAnswer.objects.create(attempt=attempt, item=item,
                                    raw=item.answer if item.number != 2 else 'не то слово')
        views._finalize(attempt, auto=False)
        self.url = reverse('vp:result', args=[attempt.public_code])
        self.right_two = self.variant.items.get(number=2).answer

    def test_owner_sees_chips_and_definitions(self):
        owner = Client()
        owner.force_login(self.user)
        response = owner.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        snake = self.variant.items.filter(block='snake').count()
        self.assertEqual(html.count('class="vp-cw '), snake)
        self.assertEqual(html.count('data-panel="'), snake)
        self.assertIn(DEFINITION, html)
        self.assertIn(f'<s>не то слово</s> {self.right_two}', html)        # зачёркнут мой, рядом верный
        self.assertIn('архив', html.split('id="vp-chain"', 1)[1].split('</div>', 1)[0])

    def test_stranger_gets_no_definition_and_no_answer(self):
        response = Client().get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('chain', response.context)          # защита — в данных, не в шаблоне
        html = response.content.decode()
        for private in (DEFINITION, self.right_two, 'не то слово', 'class="vp-cw ', 'data-panel="'):
            self.assertNotIn(private, html, private)
