# -*- coding: utf-8 -*-
"""`/healthz/` — проверка живости для healthcheck контейнера.

⚠️ Смысл проверки в том, что она умеет отвечать 503. Эндпоинт, который
отдаёт 200 всегда, — это не проверка живости, а её имитация: контейнер
считался бы здоровым с мёртвой базой, а каждая страница отдавала бы
пятисотку.
"""
from unittest import mock

from django.test import TestCase
from django.urls import reverse


class HealthzTests(TestCase):

    def test_живое_приложение_отдаёт_200(self):
        ответ = self.client.get(reverse('healthz'))
        self.assertEqual(ответ.status_code, 200)
        self.assertEqual(ответ.json(), {'ok': True})

    def test_мёртвая_база_даёт_503(self):
        with mock.patch('config.health.connection') as база:
            база.cursor.side_effect = RuntimeError('база недоступна')
            ответ = self.client.get(reverse('healthz'))
        self.assertEqual(ответ.status_code, 503)
        self.assertIn('postgres', ответ.json()['broken'])

    def test_мёртвый_кэш_даёт_503(self):
        from django.core.cache import caches

        with mock.patch.object(type(caches['default']), 'set',
                               side_effect=RuntimeError('redis недоступен')):
            ответ = self.client.get(reverse('healthz'))
        self.assertEqual(ответ.status_code, 503)
        self.assertIn('redis', ответ.json()['broken'])

    def test_наружу_не_утекают_подробности_ошибки(self):
        """В сообщениях драйверов бывают адреса и имена пользователей."""
        with mock.patch('config.health.connection') as база:
            база.cursor.side_effect = RuntimeError(
                'connection to server at "10.0.0.5", user "weconomics" failed')
            ответ = self.client.get(reverse('healthz'))
        тело = ответ.content.decode()
        self.assertNotIn('10.0.0.5', тело)
        self.assertNotIn('weconomics', тело)

    def test_ответ_не_кэшируется(self):
        """Закэшированная проверка живости показывала бы прошлое."""
        ответ = self.client.get(reverse('healthz'))
        self.assertIn('no-cache', ответ.headers.get('Cache-Control', ''))
