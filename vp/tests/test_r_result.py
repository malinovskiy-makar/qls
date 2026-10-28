"""Сессия R, фаза 6: страница результата по макетам 01/01b/01c/02.

Плашка «потеряно на записи», таблица разбора строками `<details id="zN">`, общее условие у 18,
боковая колонка. Чужому — ни плашки, ни таблицы (данных у него нет вовсе, см. фазу 5).
"""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp.models import VPAttempt
from vp.tests.helpers import load_demo

User = get_user_model()

# Та же попытка, что в `test_r_review` (копия, а не импорт: импорт продублировал бы его тесты).
ANSWERS = {5: '25000', 9: '98.0', 11: '-0.12', 13: '11 800', 14: '160 ед', 17: '1,607'}


class ResultPageTests(TestCase):
    def setUp(self):
        self.variant = load_demo('10')
        self.owner = Client()
        self.owner.force_login(User.objects.create_user('vp_rp', password='p12345'))
        self.owner.post(reverse('vp:start', args=[self.variant.slug]))
        attempt = VPAttempt.objects.get(variant=self.variant)
        self.owner.post(reverse('vp:save', args=[attempt.public_code]),
                        json.dumps({'answers': [{'item': n, 'raw': raw}
                                                for n, raw in ANSWERS.items()]}),
                        content_type='application/json')
        self.owner.post(reverse('vp:finish', args=[attempt.public_code]))
        self.url = reverse('vp:result', args=[attempt.public_code])

    def test_owner_sees_the_loss_plaque_with_pairs(self):
        html = self.owner.get(self.url).content.decode()
        self.assertIn('25 баллов потеряно на записи ответа', html)
        self.assertIn('В пяти задачах число верное', html)
        self.assertIn('30 из 100', html)
        for given, fix in (('98.0', '98,0'), ('-0.12', '-0,12'), ('11 800', '11800'),
                           ('160 ед', '160'), ('1,607', '1,61')):
            self.assertIn(f'<s>{given}</s> → <b>{fix}</b>', html)
        self.assertIn('Показать эти 5 задач', html)
        self.assertIn('Из 65 баллов, недобранных в задачах с числом, 25 – запись ответа.', html)

    def test_rows_are_details_with_links_and_shared_condition(self):
        html = self.owner.get(self.url).content.decode()
        self.assertEqual(html.count('<details class="vp-zrow is-'), 18)
        for number in range(1, 19):
            self.assertIn(f'id="z{number}"', html)
            self.assertIn(f'Ссылка на задание {number}', html)
        eighteen = html.split('id="z18"', 1)[1]
        self.assertIn('Общее условие (задача 17)', eighteen)
        self.assertNotIn('Общее условие (задача', html.split('id="z17"', 1)[1].split('id="z18"', 1)[0])
        self.assertIn('Задачи 17–18 · общее условие', html)
        self.assertIn('Тренажёр ВП</a>', html)                          # хлебные крошки
        self.assertIn('первая попытка – в таблице', html)
        self.assertIn('1-е</b> место', html)

    def test_stranger_gets_neither_plaque_nor_table(self):
        html = Client().get(self.url).content.decode()
        for private in ('потеряно на записи', 'class="vp-zrow', 'id="z1"', 'Мои попытки',
                        'class="vp-res-loss',
                        '98,0', 'Открыть таблицу'):
            self.assertNotIn(private, html, private)
        self.assertIn('Участник', html)

    def test_invite_card_only_with_an_url(self):
        self.assertNotIn('консультац', self.owner.get(self.url).content.decode())
        with mock.patch('vp.config.VP_INVITE_URL', 'https://example.test/invite'):
            self.assertIn('консультац', self.owner.get(self.url).content.decode())
