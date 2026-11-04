"""Регрессии ручной приёмки тренажёра: обещания входа и подписи окна."""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from vp import landing
from vp.models import VPAttempt
from vp.tests.helpers import load_demo


class EntryCopyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('11')

    def test_registration_copy_follows_the_available_email_flow(self):
        for enabled in (True, False):
            with self.subTest(mail=enabled), override_settings(MAIL_ENABLED=enabled):
                home = self.client.get(reverse('vp:index')).content.decode()
                intro = self.client.get(reverse('vp:intro', args=[self.variant.slug])).content.decode()
                gate = intro.split('id="vp-gate"', 1)[1].split('</dialog>', 1)[0]
                if enabled:
                    self.assertIn('Почта и пароль; почту подтвердим кодом из письма.', home)
                    self.assertNotIn('без почты', home)
                    self.assertIn('почта и пароль – почту подтвердим', gate)
                    self.assertNotIn('логин, почта', gate)
                else:
                    self.assertIn('Логин и пароль, без почты.', home)
                    self.assertIn('логин и пароль, без почты', gate)

    def test_wall_grade_is_not_repeated_for_either_dash(self):
        for dash in ('–', '—'):
            with self.subTest(dash=dash):
                self.variant.title = f'Демоверсия 2 тура {dash} 11 класс (с уточнениями)'
                self.assertEqual(landing.wall_eyebrow(self.variant),
                                 'Официальная демоверсия · 11 класс · 70 минут')

    def test_untimed_link_selects_the_promised_mode_without_starting_a_clock(self):
        self.client.force_login(get_user_model().objects.create_user('ui_untimed'))
        intro = reverse('vp:intro', args=[self.variant.slug])
        response = self.client.get(intro, {'with_timer': '0'})
        self.assertContains(response, '<input type="radio" name="with_timer" value="0" checked>', html=True)
        self.assertFalse(VPAttempt.objects.exists())
        self.client.post(reverse('vp:start', args=[self.variant.slug]), {'with_timer': '0'})
        attempt = VPAttempt.objects.get()
        self.assertFalse(attempt.with_timer)
        self.assertFalse(attempt.is_ranked)
        self.assertIsNone(attempt.expires_at)
