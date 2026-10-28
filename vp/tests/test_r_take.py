"""Сессия R, фаза 2: страница прохождения по макетам 06/07.

«±» у поля числа, метки пропусков в тексте и списки под абзацем, соотнесение
радиокнопками-буквами, навигация по разделам, «Вернуться позже», шапки разделов.
Сохранение и подсчёт — те же: сервер получает тот же словарь `{"ключ": вариант}`.
"""
import json
import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp import scoring
from vp.models import VPAnswer, VPAttempt
from vp.tests.helpers import load_demo

User = get_user_model()


def item_html(html, number):
    return html.split(f'id="vp-item-{number}"', 1)[1].split('</section>', 1)[0]


class TakePageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.client.force_login(User.objects.create_user('vp_rt', password='p12345'))

    def start(self, band):
        variant = load_demo(band)
        self.client.post(reverse('vp:start', args=[variant.slug]))
        attempt = VPAttempt.objects.get(variant=variant)
        return variant, attempt

    def page(self, attempt):
        return self.client.get(reverse('vp:take', args=[attempt.public_code])).content.decode()

    def test_demo_10_marks_lists_letters_and_plus_minus(self):
        _, attempt = self.start('10')
        html = self.page(attempt)
        self.assertEqual(len(re.findall(r'data-pm="\d+"', html)), 14)
        gaps = item_html(html, 3)
        self.assertEqual(len(re.findall(r'<a class="vp-gapmark', gaps)), 8)
        self.assertEqual(sorted(re.findall(r'<select[^>]*name="item-3\.(\d+)"', gaps), key=int),
                         [str(k) for k in range(1, 9)])
        paras = re.findall(r'<p class="vp-gap-para">(.*?)</p>', gaps, re.S)
        self.assertEqual(len(paras), 3)                  # три абзаца — три группы списков
        self.assertEqual(gaps.count('class="vp-gaplist"'), 3)
        self.assertFalse(any('<select' in p for p in paras))
        matching = item_html(html, 4)
        self.assertNotIn('<select', matching)
        self.assertEqual(re.findall(r'type="radio" name="item-4\.(\d+)"', matching),
                         ['1', '1', '2', '2', '3', '3', '4', '4'])
        self.assertIn('<b>А</b> – абсолютная бедность', matching)
        self.assertIn('aria-label="Б – относительная бедность"', matching)
        for caption in ('Все верные · 1–2', 'Пропуски · 3', 'Соотнесение · 4',
                        'Задачи с числом · 5–18'):
            self.assertIn(caption, html)
        self.assertEqual(len(re.findall(r'data-flag="\d+"', html)), 18)

    def test_demo_9_counts(self):
        _, attempt = self.start('9')
        html = self.page(attempt)
        self.assertEqual(len(re.findall(r'data-pm="\d+"', html)), 12)
        self.assertEqual(len(re.findall(r'<a class="vp-gapmark', item_html(html, 4))), 5)
        self.assertEqual(len(re.findall(r'type="radio" name="item-5\.\d+"', item_html(html, 5))), 8)
        self.assertIn('Пропуски · 4', html)

    def test_section_heads(self):
        _, attempt = self.start('10')
        html = self.page(attempt)
        self.assertIn('Задание 4 · Соотнесение', html)
        self.assertIn('9 баллов · каждая строка – своя доля', html)
        self.assertIn('9 баллов · каждый пропуск – своя доля', html)
        self.assertNotIn('по 9 баллов', html)
        self.assertIn('по 5 баллов: полный балл или ноль', html)

    def test_chosen_word_stands_in_the_mark_without_js(self):
        _, attempt = self.start('10')
        self.client.post(reverse('vp:save', args=[attempt.public_code]),
                         json.dumps({'answers': [{'item': 3, 'raw': {'1': 14}}]}),
                         content_type='application/json')
        gaps = item_html(self.page(attempt), 3)
        mark = re.search(r'<a class="vp-gapmark is-filled" href="#vp-gap-3-1".*?</a>', gaps, re.S)
        self.assertIsNotNone(mark)
        self.assertIn('развитый', mark.group(0))

    def test_form_finish_with_radios_and_autosave_erase(self):
        variant, attempt = self.start('10')
        save = reverse('vp:save', args=[attempt.public_code])
        self.client.post(save, json.dumps({'answers': [{'item': 4, 'raw': {'1': 1}}]}),
                         content_type='application/json')
        self.client.post(save, json.dumps({'answers': [{'item': 4, 'raw': {}}]}),
                         content_type='application/json')
        four = variant.items.get(number=4)
        self.assertTrue(scoring.is_blank(VPAnswer.objects.get(attempt=attempt, item=four).raw))
        self.client.post(reverse('vp:finish', args=[attempt.public_code]),
                         {'item-4.1': '2', 'item-4.3': '1'})
        answer = VPAnswer.objects.get(attempt=attempt, item=four)
        self.assertEqual(answer.raw, {'1': 2, '3': 1})
        self.assertEqual(answer.score, scoring.score_item(four, {'1': 2, '3': 1})[0])
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, answer.score)
