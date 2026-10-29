# -*- coding: utf-8 -*-
"""Вход и регистрация, раунд 3 (29.10.2026): тексты левой колонки и «Забыли пароль?».

Правки владельца после живой проверки: заголовки без тире, ссылка сброса пароля —
под полем пароля (над полем только подпись «Пароль»).
"""
import re

from django.test import TestCase, override_settings


def pitch(html):
    return re.search(r'<h1 class="au-pitch-h[^"]*">(.*?)</h1>', html, re.S).group(1)


class LoginTextTests(TestCase):
    def test_login_heading_has_no_dash(self):
        for mail in (True, False):
            with self.settings(MAIL_ENABLED=mail):
                html = self.client.get('/login/').content.decode()
            self.assertEqual(pitch(html), 'Олимпиадная экономика <em>в одном месте</em>')
            for dash in ('экономика –', 'экономика —', 'экономика -'):
                self.assertNotIn(dash, html)

    def test_forgot_link_goes_after_the_password_field(self):
        for mail in (True, False):
            with self.settings(MAIL_ENABLED=mail):
                html = self.client.get('/login/').content.decode()
            field = html.index('id="id_password"')
            forgot = html.index('Забыли пароль?')
            label = html.index('for="id_password"')
            self.assertLess(label, field)
            self.assertLess(field, forgot, 'ссылка сброса обязана идти ПОСЛЕ поля пароля')
            # Между подписью и полем — ничего, кроме самого поля.
            self.assertNotIn('au-forgot', html[label:field])
            self.assertIn('au-forgot--under', html[field:forgot + 200])


@override_settings(MAIL_ENABLED=True, ONBOARDING_ENABLED=True)
class RegisterTextTests(TestCase):
    def test_register_heading(self):
        html = self.client.get('/register/').content.decode()
        self.assertEqual(pitch(html), 'Настройте сайт <em>под себя за минуту</em>')
        self.assertNotIn('Минута', html)


class ForgotStyleTests(TestCase):
    def test_under_field_right_aligned_8px_13px_accent(self):
        from pathlib import Path

        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static/onboarding/onboarding.css').read_text(encoding='utf-8')
        under = re.search(r'\.au-forgot--under \{([^}]*)\}', css).group(1)
        self.assertIn('align-self: flex-end', under)
        # 6 px промежутка `.au-field` + 2 px = 8 px от поля.
        self.assertIn('gap: 6px', re.search(r'\.au-field \{([^}]*)\}', css).group(1))
        self.assertIn('margin-top: 2px', under)
        self.assertIn('font-size: 13px', re.search(r'^\.au-forgot \{([^}]*)\}', css, re.M).group(1))
        self.assertRegex(css, r'\.au-forgot \{ color: var\(--accent-ink\)|, \.au-forgot \{ color: var\(--accent-ink\)')
