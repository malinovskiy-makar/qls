"""Сессия R, фаза 9: посадочная по макету 04.

Отсчёт до тура из `config.TOUR_DATES`, полоса долей из данных, пробник записи, «что дальше»
по приоритету. Инвариант «без прокрутки на 1440×800» держит браузерная проверка
(`browser_take.mjs`) и глаз владельца.
"""
import json
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp import landing
from vp.models import VPAttempt, VPVariant
from vp.tests.helpers import load_demo

User = get_user_model()
ANSWERS = {5: '25000', 9: '98.0', 11: '-0.12', 13: '11 800', 14: '160 ед', 17: '1,607'}


class CountdownTests(TestCase):
    def test_days_before_during_and_after(self):
        self.assertEqual(landing.countdown(date(2026, 10, 25)), 'до тура 19 дней')
        self.assertEqual(landing.countdown(date(2026, 11, 12)), 'до тура 1 день')
        self.assertEqual(landing.countdown(date(2026, 11, 13)), 'тур идёт')
        self.assertEqual(landing.countdown(date(2026, 11, 22)), 'тур идёт')
        self.assertIsNone(landing.countdown(date(2026, 11, 23)))

    def test_page_uses_the_local_date(self):
        load_demo('10')
        with mock.patch('django.utils.timezone.localdate', return_value=date(2026, 10, 25)):
            html = Client().get(reverse('vp:index')).content.decode()
        self.assertIn('до тура 19 дней', html)
        with mock.patch('django.utils.timezone.localdate', return_value=date(2026, 11, 23)):
            html = Client().get(reverse('vp:index')).content.decode()
        self.assertNotIn('до тура', html)
        self.assertNotIn('тур идёт', html)


class LandingTests(TestCase):
    def setUp(self):
        for band in ('9', '10', '11'):
            load_demo(band)

    def test_composition_shares_come_from_the_data(self):
        response = Client().get(reverse('vp:index'))
        rows = response.context['composition']['rows']
        self.assertEqual([r['total'] for r in rows],
                         [Decimal('12'), Decimal('9'), Decimal('9'), Decimal('70')])
        self.assertEqual([r['percent'] for r in rows], [12, 9, 9, 70])       # ширины — доли баллов
        html = response.content.decode()
        self.assertIn('style="width: 70.00%" data-points="70"', html)
        self.assertIn('10–11 класс: 18 заданий · 70 минут · 100 баллов', html)
        self.assertIn('id="vp-probe"', html)
        self.assertIn('data-probe="37.5"', html)

    def test_guest_has_no_my_band(self):
        response = Client().get(reverse('vp:index'))
        self.assertIsNone(response.context['mine'])
        html = response.content.decode()
        self.assertNotIn('Моя лучшая попытка', html)
        self.assertIn('Чтобы пройти вариант, нужна короткая бесплатная регистрация', html)

    def test_what_next_after_a_format_loss(self):
        client = Client()
        client.force_login(User.objects.create_user('vp_rl', password='p12345'))
        variant = load_demo('10')
        client.post(reverse('vp:start', args=[variant.slug]))
        attempt = VPAttempt.objects.get(variant=variant)
        client.post(reverse('vp:save', args=[attempt.public_code]),
                    json.dumps({'answers': [{'item': n, 'raw': raw} for n, raw in ANSWERS.items()]}),
                    content_type='application/json')
        client.post(reverse('vp:finish', args=[attempt.public_code]))
        response = client.get(reverse('vp:index'))
        self.assertEqual(response.context['mine']['step'], 'drill_loss')
        html = response.content.decode()
        self.assertIn('На записи потеряно 25 баллов', html)
        self.assertIn('в прошлой попытке', html)
        self.assertIn('Тренировка записи ответа', html)
        self.assertIn('Лучшая попытка · 10 класс', html)
        self.assertNotIn('Моя лучшая попытка', html)
        self.assertIn(reverse('vp:drill'), html)


# Заголовки карточек «моё» – существительные (решение владельца 30.10.2026). Старые обороты
# («Моя …», «Что дальше», обещание про таблицу) на посадочной возвращаться не должны.
# ⚠️ «Таблица своя у каждого класса» стоит и в блоке правил (`_rules.html`, он включён в страницу,
# там после слова «класса» двоеточие – владелец просил его не трогать), поэтому ищем хвост
# подзаголовка таблицы целиком: с пробелом перед фразой и точкой после неё.
GONE_ON_LANDING = ('Что дальше', 'Моя лучшая попытка', 'попадёт в таблицу',
                   ' Таблица своя у каждого класса.')


class LandingCardTitlesTests(TestCase):
    def setUp(self):
        for band in ('9', '10', '11'):
            load_demo(band)

    def _page(self, client):
        return client.get(reverse('vp:index')).content.decode()

    def test_guest_page_has_no_old_phrases(self):
        html = self._page(Client())
        for gone in GONE_ON_LANDING:
            self.assertNotIn(gone, html, gone)
        self.assertIn('Первая попытка по варианту, с таймером. При равных баллах выше тот, '
                      'кто сдал быстрее.</p>', html)

    def test_student_without_attempts_sees_next_variant_and_best_titles(self):
        client = Client()
        client.force_login(User.objects.create_user('vp_titles', password='p12345'))
        response = client.get(reverse('vp:index'))
        html = response.content.decode()
        self.assertEqual(response.context['mine']['step'], 'next')
        for gone in GONE_ON_LANDING:
            self.assertNotIn(gone, html, gone)
        self.assertNotIn('Первая попытка с таймером по любому варианту', html)
        self.assertIn('Лучшая попытка', html)
        self.assertIn('Следующий вариант', html)

    def test_student_with_nothing_to_open_gets_the_drill_card(self):
        # Нетронутых вариантов своего класса нет → последнее `else`: тренировка записи.
        VPVariant.objects.all().delete()
        client = Client()
        client.force_login(User.objects.create_user('vp_titles3', password='p12345'))
        response = client.get(reverse('vp:index'))
        html = response.content.decode()
        self.assertEqual(response.context['mine']['step'], 'drill')
        for gone in GONE_ON_LANDING:
            self.assertNotIn(gone, html, gone)
        self.assertIn('Лучшая попытка', html)
        self.assertIn('Тренировка записи ответа', html)
        self.assertIn('12 готовых чисел', html)
        self.assertIn('2–3 минуты', html)
        self.assertNotIn('Потренировать запись ответа', html)

    def test_started_attempt_card_is_titled_by_state(self):
        client = Client()
        client.force_login(User.objects.create_user('vp_titles2', password='p12345'))
        client.post(reverse('vp:start', args=[load_demo('10').slug]))
        html = self._page(client)
        self.assertEqual(client.get(reverse('vp:index')).context['mine']['step'], 'continue')
        self.assertIn('Начатая попытка', html)
        self.assertIn('время идёт', html)
        for gone in GONE_ON_LANDING:
            self.assertNotIn(gone, html, gone)
