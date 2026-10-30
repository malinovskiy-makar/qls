# -*- coding: utf-8 -*-
"""Кнопка «Проблема или предложение» не рисуется огромной, пока страница грузится.

⚠️ ДЕФЕКТ БЫЛ В ПОРЯДКЕ, А НЕ В ПРАВИЛЕ. Размер значка задавался только
правилом `.fb-btn svg` в `_feedback.html`, а этот партиал подключается в самом
конце <body>: до его разбора SVG рисовался размером браузера по умолчанию.
Поэтому проверки здесь — про ПОРЯДОК на отрисованной странице и про атрибуты
размера у SVG, а не про само наличие правила (фаза 3 ночной сессии 15.09.2026).
"""
import io
import re

from django.test import TestCase

from problems.models import User

PASSWORD = 'fb-style-probe-2026'
BUTTON = 'class="fb-btn'
RULE = '.fb-btn svg {'
SVG_OF_BUTTON = re.compile(r'class="fb-btn[^"]*"[^>]*>\s*<svg([^>]*)>')


class FeedbackButtonStyleOrderTests(TestCase):

    def _check_page(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        html = response.content.decode('utf-8')
        button = html.find(BUTTON)
        rule = html.find(RULE)
        self.assertNotEqual(button, -1, '%s: кнопки нет' % url)
        self.assertNotEqual(rule, -1, '%s: правила размера значка нет' % url)
        self.assertLess(rule, button,
                        '%s: правило размера значка разобрано ПОЗЖЕ кнопки' % url)
        # Размер стоит и атрибутами — страховка на случай, если стиль не
        # пришёл вовсе. Пустой перебор — не «зелено»: значок обязан найтись.
        svgs = [m.group(1) for m in SVG_OF_BUTTON.finditer(html)]
        self.assertTrue(svgs, '%s: у кнопки не нашлось значка' % url)
        for attrs in svgs:
            self.assertIn('width="15"', attrs, url)
            self.assertIn('height="15"', attrs, url)

    def test_guest_pages(self):
        for url in ('/catalog/', '/game/', '/calc2/', '/login/', '/register/'):
            self._check_page(url)

    def test_cabinet_pages(self):
        user = User.objects.create_user(username='fb_style_student',
                                        password=PASSWORD, role='student')
        self.client.force_login(user)
        for url in ('/student/', '/profile/'):
            self._check_page(url)

    def test_feedback_partial_keeps_no_button_rules(self):
        """В `_feedback.html` остаются стили окна, кружка Telegram и печати."""
        src = io.open('templates/_feedback.html', encoding='utf-8').read()
        for head in ('.fb-btn {', '.fb-btn svg {', '.fb-btn.is-busy {',
                     '.fb-btn--onpage {', '.fb-btn .fb-btn-text {'):
            # assertFalse, а не assertNotIn: тот напечатал бы в отчёт весь файл.
            self.assertFalse(head in src, 'в _feedback.html осталось правило %s' % head)


class AuthScreensFloatingButtonTests(TestCase):
    """Вход и регистрация: кнопка обратной связи — плавающий круг, а не кнопка в шапке
    (решение владельца 30.10.2026; шапки сайта на этих экранах нет)."""

    def test_floating_button_is_on_login_and_register(self):
        for url in ('/login/', '/register/'):
            html = self.client.get(url).content.decode('utf-8')
            self.assertIn('class="fb-btn fb-btn--onpage fb-btn--fab"', html, url)
            self.assertIn('aria-label="Проблема или предложение"', html, url)
            # Правило круга разобрано ДО кнопки и держит её в углу окна, над кружком Telegram.
            rule = html.find('.fb-btn--fab {')
            self.assertNotEqual(rule, -1, url)
            self.assertLess(rule, html.find('class="fb-btn fb-btn--onpage fb-btn--fab"'), url)
            self.assertIn('position: fixed; right: 16px; bottom: 79px', html, url)
            # Пока открыто окно cookie, круг Telegram поднят на его высоту, и этот круг тоже.
            self.assertIn('.ck-bar:not([hidden])) .fb-btn--fab { bottom: calc(79px + var(--ck-h', html, url)
            # На телефоне круг уходит в полосу с логотипом, чтобы не лечь на кнопку формы.
            self.assertIn('position: absolute; top: 8px; right: 16px; bottom: auto', html, url)
            # Шапку сайта на входе не возвращаем: только полоса с логотипом.
            self.assertNotIn('class="nav-', html, url)

