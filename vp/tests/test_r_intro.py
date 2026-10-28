"""Сессия R, фаза 10: интро варианта по макету 05.

Одна колонка: таблица «Из чего состоит вариант» со столбцом «Как считается», плашка правила
записи со ссылкой на тренировку, режим плитками-радио, «Начать вариант». Стена гостю и
«Продолжить вариант» — как раньше.
"""
import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp.tests.helpers import load_demo

User = get_user_model()


class IntroTests(TestCase):
    def setUp(self):
        self.variant = load_demo('10')
        self.url = reverse('vp:intro', args=[self.variant.slug])
        self.client = Client()
        self.client.force_login(User.objects.create_user('vp_ri', password='p12345'))

    def test_table_with_how_column(self):
        html = self.client.get(self.url).content.decode()
        table = html.split('id="vp-blocks"', 1)[1].split('</table>', 1)[0]
        self.assertEqual(len(re.findall(r'<tr data-block="', table)), 4)
        self.assertIn('Как считается', table)
        for how in ('верный вариант – доля балла, лишний отнимает долю',
                    'каждый пропуск – своя доля, штрафа нет',
                    'каждая строка – своя доля, штрафа нет',
                    'по 5 баллов: полный балл или ноль'):
            self.assertIn(how, table)
        self.assertNotIn('по 9 баллов', html)
        self.assertNotIn('задании 3–4', html)
        self.assertNotIn('Как считаются баллы', html)

    def test_meta_rule_plaque_drill_link_and_modes(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('Демоверсия ВШЭ · 2026/27 · 18 заданий · 100 баллов', html)
        self.assertIn('Ответ-число в неверной записи – 0 баллов, как на туре', html)
        self.assertIn(reverse('vp:drill'), html)
        self.assertIn('Потренировать запись – 2 минуты', html)
        self.assertIn('Первая попытка идёт в таблицу 10 класса.', html)
        self.assertIn('Без ограничения по времени. В таблицу не идёт.', html)
        self.assertIn('Ответы сохраняются сами. Закрыли вкладку – продолжите с того же места, '
                      'таймер при этом идёт.', html)
        self.assertLess(html.index('Начать вариант'), html.index('</form>'))

    def test_guest_gets_the_wall_and_owner_of_a_started_one_continues(self):
        html = Client().get(self.url).content.decode()
        self.assertIn('id="vp-gate"', html)
        self.assertIn('Пройти вариант можно только после короткой бесплатной регистрации.', html)
        self.client.post(reverse('vp:start', args=[self.variant.slug]))
        html = self.client.get(self.url).content.decode()
        self.assertIn('Продолжить вариант', html)
        self.assertNotIn('name="with_timer"', html)
