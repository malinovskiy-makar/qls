"""Сессия R-fix, фаза 2: короткая мета варианта, архив 1 тура на результате, метка «до сотых».

* мета без хвоста `author` / `source_note` — на экране вариантов, интро и в «Моих попытках»;
* результат попытки скрытого тура: «архив 1 тура», без места, «в таблице» и «Этот же
  вариант без таймера» (интро скрытого варианта ученику — 404); у 2 тура всё на месте;
* счётчик «В таблице» в «Моих попытках» не считает попытку скрытого тура.
"""
import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from vp import views
from vp.models import VPAnswer, VPAttempt
from vp.tests.helpers import load_demo, make_full_variant
from vp.tests.test_rfix_phone import STYLES, _rule

User = get_user_model()

TAIL = ('Методическая', 'Официальная')


class MetaTests(TestCase):
    def setUp(self):
        self.variant = load_demo('10')
        # Хвост, который убираем, в данных есть — иначе тест ничего бы не проверял.
        self.assertIn('Методическая', self.variant.author)
        self.assertIn('Официальная', self.variant.source_note)
        self.client = Client()
        self.client.force_login(User.objects.create_user('vp_rf_meta', password='p12345'))

    def test_variant_card_meta_is_short(self):
        html = self.client.get(reverse('vp:variants') + '?band=10').content.decode()
        card = re.search(r'<article class="vp-vcard.*?</article>', html, re.S).group(0)
        self.assertEqual(re.findall(r'<p class="vp-vcard-m">(.*?)</p>', card),
                         ['2026/27 · 18 заданий · 70 мин'])
        self.assertIn('Демоверсия ВШЭ', card)                       # надзаголовок остался
        self.assertNotIn('<span class="vp-vcard-src">', card)        # года в углу нет
        for tail in TAIL:
            self.assertNotIn(tail, card)

    def test_intro_meta_is_exact(self):
        html = self.client.get(reverse('vp:intro', args=[self.variant.slug])).content.decode()
        self.assertEqual(re.findall(r'<div class="vp-sub">(.*?)</div>', html),
                         ['Демоверсия ВШЭ · 2026/27 · 18 заданий · 100 баллов'])
        for tail in TAIL:
            self.assertNotIn(tail, html)

    def test_my_attempts_meta_without_numbers(self):
        self.client.post(reverse('vp:start', args=[self.variant.slug]))
        html = self.client.get(reverse('vp:my')).content.decode()
        self.assertIn('<small>Демоверсия ВШЭ · 2026/27</small>', html)
        for tail in TAIL:
            self.assertNotIn(tail, html)


class ArchiveResultTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('vp_rf_arch', password='p12345')
        self.client = Client()
        self.client.force_login(self.user)
        # Попытка 1 тура (скрытого): зачётная, с таймером, сдана.
        old = make_full_variant('vp-rf-tour1')
        old.is_published = True
        old.save()
        attempt = VPAttempt.objects.create(
            variant=old, user=self.user, public_code=views._new_code(), with_timer=True,
            is_ranked=True, max_score=old.max_score,
            expires_at=timezone.now() + timedelta(minutes=30))
        VPAnswer.objects.create(attempt=attempt, item=old.items.get(number=1),
                                raw=old.items.get(number=1).answer)
        views._finalize(attempt, auto=False)
        self.archived_url = reverse('vp:result', args=[attempt.public_code])
        # Попытка 2 тура: первая с таймером — в таблице; 17-е — «1,607».
        self.variant = load_demo('10')
        self.client.post(reverse('vp:start', args=[self.variant.slug]))
        current = VPAttempt.objects.get(variant=self.variant)
        self.client.post(reverse('vp:save', args=[current.public_code]),
                         json.dumps({'answers': [{'item': 17, 'raw': '1,607'}]}),
                         content_type='application/json')
        self.client.post(reverse('vp:finish', args=[current.public_code]))
        self.current_url = reverse('vp:result', args=[current.public_code])

    def test_tour_1_result_is_an_archive(self):
        self.assertFalse(self.user.is_staff)
        html = self.client.get(self.archived_url).content.decode()
        self.assertIn('архив 1 тура', html)
        for gone in ('Открыть таблицу', 'в таблице', 'Этот же вариант без таймера', '-е</b> место'):
            self.assertNotIn(gone, html, gone)
        self.assertIn('Пройти другой вариант', html)
        self.assertNotIn('Что дальше', html)              # без карточек «Что дальше» пустой

    def test_tour_2_result_keeps_the_table(self):
        html = self.client.get(self.current_url).content.decode()
        for kept in ('первая попытка – в таблице', 'Открыть таблицу', '1-е</b> место',
                     'Этот же вариант без таймера', 'Что дальше'):
            self.assertIn(kept, html, kept)
        self.assertNotIn('архив 2 тура', html)

    def test_ranked_counter_skips_the_hidden_tour(self):
        html = self.client.get(reverse('vp:my')).content.decode()
        self.assertIn('Все · 2', html)
        self.assertIn('В таблице · 1', html)
        ranked = self.client.get(reverse('vp:my') + '?f=ranked').content.decode()
        self.assertIn(self.current_url, ranked)
        self.assertNotIn(self.archived_url, ranked)

    def test_decimals_reason_label(self):
        html = self.client.get(self.current_url).content.decode()
        self.assertIn('<span class="vp-ztag">до сотых</span>', html)
        self.assertNotIn('>знаки<', html)


class LandingCaptionStyleTests(SimpleTestCase):
    def test_caption_may_take_two_lines(self):
        # В одну строку многоточие резало главное: «…потеряно 25 ба…», «… · 00:…».
        rule = _rule(STYLES.read_text(encoding='utf-8'), '.vp-land-cs')
        self.assertEqual(rule.get('-webkit-line-clamp'), '2')
        self.assertNotIn('white-space', rule)
