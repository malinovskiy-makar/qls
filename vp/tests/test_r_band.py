"""Сессия R, фаза 3: класс ученика (`landing.student_band`) — везде один.

Ученице 10 класса посадочная, экран вариантов и «моё» предлагают 10 класс; явный выбор
(`?band=`, `?board=`, вкладка со скриптом через POST `/vp/band/`) запоминается.
"""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp.models import VPAttempt
from vp.tests.helpers import load_demo

User = get_user_model()


class StudentBandTests(TestCase):
    def setUp(self):
        self.demos = {band: load_demo(band) for band in ('9', '10', '11')}
        self.client = Client()
        self.client.force_login(User.objects.create_user('vp_band', password='p12345'))
        variant = self.demos['10']
        self.client.post(reverse('vp:start', args=[variant.slug]))
        attempt = VPAttempt.objects.get(variant=variant)
        self.client.post(reverse('vp:save', args=[attempt.public_code]),
                         json.dumps({'answers': [{'item': 5, 'raw': '25000'}]}),
                         content_type='application/json')
        self.client.post(reverse('vp:finish', args=[attempt.public_code]))

    def landing_tab(self, client=None):
        response = (client or self.client).get(reverse('vp:index'))
        active = [b['band'] for b in response.context['boards'] if b['active']]
        return active, response

    def variants_band(self, client=None):
        return (client or self.client).get(reverse('vp:variants')).context['current']['code']

    def test_tenth_grader_sees_tenth_grade_everywhere(self):
        active, response = self.landing_tab()
        self.assertEqual(active, ['10'])
        self.assertContains(response, 'data-board-tab="10" aria-selected="true"')
        self.assertEqual(self.variants_band(), '10')
        mine = response.context['mine']
        self.assertTrue(mine['next_variant'] is None or mine['next_variant'].grade_band == '10')
        self.assertEqual((mine['done'], mine['total']), (1, 1))
        self.assertContains(response, 'Пройдено · 10 класс')

    def test_explicit_choice_is_remembered(self):
        self.client.get(reverse('vp:variants') + '?band=11')
        self.assertEqual(self.landing_tab()[0], ['11'])
        self.assertEqual(self.variants_band(), '11')
        response = self.client.post(reverse('vp:remember_band'), '9', content_type='text/plain')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.landing_tab()[0], ['9'])
        self.assertEqual(self.variants_band(), '9')

    def test_unknown_band_is_refused(self):
        response = self.client.post(reverse('vp:remember_band'), '7', content_type='text/plain')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.landing_tab()[0], ['10'])

    def test_guest_gets_the_first_band(self):
        guest = Client()
        self.assertEqual(self.landing_tab(guest)[0], ['9'])
        self.assertEqual(self.variants_band(guest), '9')

    def test_no_class_column_and_first_place_caption(self):
        _, response = self.landing_tab()
        html = response.content.decode()
        head = html.split('vp-land-row is-head', 1)[1].split('</div>', 1)[0]
        self.assertNotIn('Класс', head)
        self.assertIn('Вы на первом месте.', html)
        self.assertNotIn('выше можно подняться', html)
        self.assertIn('vp-land-row is-me', html)
