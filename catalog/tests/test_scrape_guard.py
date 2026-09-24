# -*- coding: utf-8 -*-
"""Квота РАЗНЫХ задач (24.09.2026, ADR 0129, `catalog/scrape_guard.py`)."""
import socket
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog import scrape_guard
from problems.tests.factories import make_problem, make_user

GOOGLEBOT = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
BOT_IP = '66.249.66.1'


# ⚠️ Свой кэш: у LocMemCache по умолчанию 300 ключей, и 600 задач вытеснили бы
# отметки «видел задачу». На бою кэш — Redis без такого предела.
def _big_cache():
    from django.conf import settings
    caches = {name: dict(conf) for name, conf in settings.CACHES.items()}
    caches['default'] = {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                         'LOCATION': 'scrape-guard-tests', 'OPTIONS': {'MAX_ENTRIES': 100000}}
    return caches


BIG_CACHE = _big_cache()


@override_settings(CACHES=BIG_CACHE, SCRAPE_GUARD_ENABLED=True, SCRAPE_QUOTA_IP_HOUR=1000,
                   SCRAPE_QUOTA_IP_DAY=600, SCRAPE_QUOTA_USER_HOUR=1000,
                   SCRAPE_QUOTA_USER_DAY=1000)
class ScrapeGuardTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ids = [make_problem('Задача номер %d про спрос.' % i).pk for i in range(1001)]

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _open(self, pid, **extra):
        return self.client.get(reverse('catalog:problem_detail', args=[pid]), **extra)

    def _walk(self, count, **extra):
        """Открыть `count` разных задач через функцию квоты — быстро, без рендера."""
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        rf = RequestFactory()
        for pid in self.ids[:count]:
            request = rf.get('/', **extra)
            request.user = extra.pop('_user', None) or AnonymousUser()
            self.assertIsNone(scrape_guard.check(request, pid), pid)

    def test_601st_distinct_problem_from_one_ip_is_429(self):
        self._walk(600, HTTP_X_REAL_IP='7.7.7.7')
        response = self._open(self.ids[600], HTTP_X_REAL_IP='7.7.7.7')
        self.assertEqual(response.status_code, 429)
        self.assertIn('Слишком много задач подряд', response.content.decode())
        # Уже открытая задача — открывается.
        self.assertEqual(self._open(self.ids[0], HTTP_X_REAL_IP='7.7.7.7').status_code, 200)
        # Другой адрес — свои счётчики.
        self.assertEqual(self._open(self.ids[600], HTTP_X_REAL_IP='8.8.8.8').status_code, 200)
        # Окно ?pane=1 — JSON 429, не страница.
        pane = self.client.get(reverse('catalog:problem_detail', args=[self.ids[601]]),
                               {'pane': '1'}, HTTP_X_REAL_IP='7.7.7.7')
        self.assertEqual(pane.status_code, 429)
        self.assertEqual(pane.json(), {'error': 'scrape'})

    def test_signed_in_under_the_limit_is_not_blocked(self):
        user = make_user('reader_many')
        self.client.force_login(user)
        for pid in self.ids[:700]:
            request = mock.Mock(user=user, META={'HTTP_X_REAL_IP': '7.7.7.7'})
            self.assertIsNone(scrape_guard.check(request, pid))
        self.assertEqual(self._open(self.ids[700], HTTP_X_REAL_IP='7.7.7.7').status_code, 200)

    def _dns(self, host, addresses):
        return mock.patch.multiple(socket, gethostbyaddr=mock.Mock(return_value=(host, [], [BOT_IP])),
                                   getaddrinfo=mock.Mock(return_value=[(0, 0, 0, '', (a, 0))
                                                                       for a in addresses]))

    def test_verified_googlebot_is_not_limited(self):
        with self._dns('crawl-66-249-66-1.googlebot.com', [BOT_IP]):
            self._walk(1000, HTTP_X_REAL_IP=BOT_IP, HTTP_USER_AGENT=GOOGLEBOT)
            response = self._open(self.ids[1000], HTTP_X_REAL_IP=BOT_IP, HTTP_USER_AGENT=GOOGLEBOT)
        self.assertEqual(response.status_code, 200)

    def test_fake_googlebot_is_limited_and_logged(self):
        with self._dns('host.evil.example', ['10.0.0.1']), \
                self.assertLogs('security', 'WARNING') as logs:
            self._walk(600, HTTP_X_REAL_IP='9.9.9.9', HTTP_USER_AGENT=GOOGLEBOT)
            response = self._open(self.ids[600], HTTP_X_REAL_IP='9.9.9.9', HTTP_USER_AGENT=GOOGLEBOT)
        self.assertEqual(response.status_code, 429)
        self.assertTrue(any('поддельный поисковый робот' in line for line in logs.output))

    def test_dns_failure_is_ordinary_visitor(self):
        with mock.patch.object(socket, 'gethostbyaddr', side_effect=socket.herror('нет')):
            self._walk(600, HTTP_X_REAL_IP='6.6.6.6', HTTP_USER_AGENT=GOOGLEBOT)
            response = self._open(self.ids[600], HTTP_X_REAL_IP='6.6.6.6', HTTP_USER_AGENT=GOOGLEBOT)
        self.assertEqual(response.status_code, 429)

    def test_scrape_report_names_the_heavy_reader(self):
        self._walk(60, HTTP_X_REAL_IP='5.5.5.5')
        out = StringIO()
        call_command('scrape_report', stdout=out)
        self.assertIn('5.5.5.5', out.getvalue())
        self.assertIn('60', out.getvalue())
