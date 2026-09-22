"""Дымовая проверка трёх экранов сессии 5: отрисовываются вообще.

Содержательные инварианты — в `test_landing`, `test_variants`, `test_my`;
здесь только «страница отдалась, а не упала пятисоткой», гостю и вошедшему,
на пустых и на заполненных данных.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp.tests.helpers import make_published

User = get_user_model()


class ScreensRenderTests(TestCase):

    def test_01_empty_database_renders_every_screen(self):
        """Ни одного варианта: экраны всё равно открываются, а не падают."""
        client = Client()
        client.force_login(User.objects.create_user('smoke_empty', password='p12345'))
        for name in ('vp:index', 'vp:variants', 'vp:my'):
            with self.subTest(name):
                self.assertEqual(client.get(reverse(name)).status_code, 200)

    def test_02_guest_sees_the_landing_and_the_variants(self):
        make_published('smoke-v')
        guest = Client()
        self.assertEqual(guest.get(reverse('vp:index')).status_code, 200)
        self.assertEqual(guest.get(reverse('vp:variants')).status_code, 200)
        self.assertEqual(guest.get(reverse('vp:intro', args=['smoke-v'])).status_code, 200)

    def test_03_logged_in_person_sees_all_four_screens(self):
        variant = make_published('smoke-w')
        client = Client()
        client.force_login(User.objects.create_user('smoke_in', password='p12345'))
        client.post(reverse('vp:start', args=[variant.slug]), {'with_timer': '1'})
        for name in ('vp:index', 'vp:variants', 'vp:my'):
            with self.subTest(name):
                self.assertEqual(client.get(reverse(name)).status_code, 200)
        self.assertEqual(client.get(reverse('vp:intro', args=['smoke-w'])).status_code, 200)
