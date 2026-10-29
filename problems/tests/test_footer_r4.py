# -*- coding: utf-8 -*-
"""Подвал и шапка, раунд 4 (решения владельца 29.10.2026).

Подвал сайта (метка версии + строка документов) — ТОЛЬКО на главной, в профиле,
на /legal/ и на входе/регистрации (там дают согласие). Везде остальное его нет.
Окно согласия на cookie — не подвал: оно на всех страницах. Шапки сайта нет на
входе, регистрации, экранах почты и сервисов и в онбординге.
"""
import time
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from problems.models_platform import UserProfile
from problems.tests.factories import make_problem, make_user

FOOTER = '<p class="legal-foot">'
VERSION = '<div class="site-version">'
SITE_NAV = '<nav class="site-nav">'
COOKIE = ('id="cookie-bar"', 'cookie_bar.js')


def html_of(response):
    return response.content.decode('utf-8')


class FooterPagesTests(TestCase):
    def setUp(self):
        self.student = make_user('foot_st')
        self.teacher = make_user('foot_tu', role='teacher')
        self.problem = make_problem('Условие.', title='Задача')

    def get(self, url, user=None):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200, url)
        return html_of(response)

    def with_footer(self):
        return [
            ('/', None), ('/profile/', self.student), ('/profile/?tab=data', self.student),
            ('/legal/', None), ('/legal/privacy/', None), ('/login/', None), ('/register/', None),
        ]

    def without_footer(self):
        return [
            ('/catalog/', None), ('/catalog/', self.student),
            (reverse('catalog:problem_detail', args=[self.problem.pk]), None),
            ('/calc2/', self.student), ('/textbook/', None), ('/olympiads/', None),
            ('/vp/', None), ('/game/', None), ('/student/', self.student),
            ('/teacher/groups/', self.teacher), ('/welcome/role/', self.student),
        ]

    def test_footer_is_on_home_profile_legal_login_register(self):
        for url, user in self.with_footer():
            html = self.get(url, user)
            self.assertEqual(html.count(FOOTER), 1, url)
            self.assertEqual(html.count(VERSION), 1, url)
            for href in ('/legal/', '/legal/privacy/', '/legal/terms/', '/legal/recommendations/'):
                self.assertIn('href="%s"' % href, html.split(FOOTER, 1)[1], url)
            self.assertIn('data-cookie-settings', html, url)
            self.assertIn('class="legal-foot-age"', html, url)

    def test_footer_is_gone_everywhere_else(self):
        for url, user in self.without_footer():
            html = self.get(url, user)
            self.assertNotIn(FOOTER, html, url)
            self.assertNotIn(VERSION, html, url)

    def test_cookie_window_is_on_every_page(self):
        for url, user in self.with_footer() + self.without_footer():
            html = self.get(url, user)
            for marker in COOKIE:
                self.assertIn(marker, html, url)


class FooterTemplatesTests(TestCase):
    """Подвал — блоком шаблона, а не условием по адресу."""

    def roots(self):
        base = Path(settings.BASE_DIR)
        paths = list(base.glob('templates/**/*.html')) + list(base.glob('*/templates/**/*.html'))
        for path in paths:
            if path.relative_to(base).parts[0].startswith(('venv', 'node_modules')):
                continue
            text = path.read_text(encoding='utf-8')
            if '<!doctype html' in text.lower():
                yield path.relative_to(base).as_posix(), text

    def test_no_root_includes_the_footer_outside_a_block(self):
        own = {'legal/templates/legal/accept.html'}       # /legal/accept/ — тоже документы
        for rel, text in self.roots():
            if rel in own:
                continue
            self.assertNotIn("{% include '_legal_footer.html' %}", text, rel)
            if "_site_footer.html" in text or '{% block site_footer %}' in text:
                self.assertIn('{% block site_footer %}', text, rel)

    def test_age_mark_is_its_own_partial(self):
        footer = (Path(settings.BASE_DIR) / 'templates/_legal_footer.html').read_text(encoding='utf-8')
        self.assertIn("{% include '_age_mark.html' %}", footer)


class NoSiteNavTests(TestCase):
    """Тёмной шапки сайта нет на входе, регистрации, экранах почты и сервисов, онбординге."""

    @override_settings(MAIL_ENABLED=True)
    def test_login_register_and_their_children_have_only_the_logo_bar(self):
        for url in ('/login/', '/register/', '/password/forgot/'):
            html = html_of(self.client.get(url))
            self.assertNotIn(SITE_NAV, html, url)
            self.assertNotIn('Проблема или предложение', html.split('</header>', 1)[0], url)
            self.assertIn('<header class="au-top">', html, url)
            self.assertIn('href="/" aria-label="Weconomics: на главную"', html, url)

    @override_settings(SOCIAL_LOGIN_ENABLED=True, VK_ID_CLIENT_ID='51234567')
    def test_almost_done_and_service_error_have_no_site_nav(self):
        session = self.client.session
        session['social_pending'] = {'provider': 'vk', 'uid': '1', 'first_name': 'Иван',
                                     'email': '', 'at': time.time()}
        session.save()
        finish = html_of(self.client.get('/auth/finish/'))
        self.assertIn('Почти готово', finish)
        error = html_of(self.client.get('/auth/vk/callback/', {'state': 'x', 'code': 'y'}))
        for html in (finish, error):
            self.assertNotIn(SITE_NAV, html)
            self.assertIn('<header class="au-top">', html)
            self.assertIn(FOOTER, html)

    def test_onboarding_has_no_site_nav_and_no_footer(self):
        user = make_user('foot_ob')
        self.client.force_login(user)
        UserProfile.objects.filter(user=user).update(role='student', grade='10', level='basic')
        for url in ('/welcome/role/', '/welcome/goals/'):
            html = html_of(self.client.get(url))
            self.assertNotIn(SITE_NAV, html, url)
            self.assertNotIn(FOOTER, html, url)
            self.assertIn('id="cookie-bar"', html, url)
