# -*- coding: utf-8 -*-
"""`/health/` — публичная проверка живости для внешнего мониторинга.

В отличие от `/healthz/` (config/tests/test_healthz.py) этот адрес открыт
без авторизации и отчитывается по каждому компоненту отдельно — тесты
проверяют, что 503 приходит именно с тем полем false, которое сломано,
а не общим «что-то не так».
"""
from unittest import mock

from django.test import TestCase
from django.urls import reverse


class HealthTests(TestCase):

    def test_живое_приложение_отдаёт_200(self):
        ответ = self.client.get(reverse('health'))
        self.assertEqual(ответ.status_code, 200)
        self.assertEqual(ответ.json(), {
            'status': 'ok',
            'db': True,
            'redis_default': True,
            'redis_sessions': True,
        })

    def test_мёртвая_база_даёт_503_db_false(self):
        with mock.patch('config.health.connection') as база:
            база.cursor.side_effect = RuntimeError('база недоступна')
            ответ = self.client.get(reverse('health'))
        тело = ответ.json()
        self.assertEqual(ответ.status_code, 503)
        self.assertEqual(тело['status'], 'error')
        self.assertFalse(тело['db'])
        self.assertTrue(тело['redis_default'])
        self.assertTrue(тело['redis_sessions'])

    def test_мёртвый_default_redis_даёт_503_redis_default_false(self):
        from django.core.cache import caches

        # ⚠️ Патчим ИНСТАНС, не класс: 'default' и 'sessions' в тестовом
        # окружении (без REDIS_URL) — оба LocMemCache, один класс на двоих.
        # Патч type(...).set сломал бы оба алиаса разом, а тест должен
        # проверить именно избирательный сбой одного из двух.
        with mock.patch.object(caches['default'], 'set',
                               side_effect=RuntimeError('redis недоступен')):
            ответ = self.client.get(reverse('health'))
        тело = ответ.json()
        self.assertEqual(ответ.status_code, 503)
        self.assertTrue(тело['db'])
        self.assertFalse(тело['redis_default'])
        self.assertTrue(тело['redis_sessions'])

    def test_мёртвый_sessions_redis_даёт_503_redis_sessions_false(self):
        from django.core.cache import caches

        with mock.patch.object(caches['sessions'], 'set',
                               side_effect=RuntimeError('redis недоступен')):
            ответ = self.client.get(reverse('health'))
        тело = ответ.json()
        self.assertEqual(ответ.status_code, 503)
        self.assertTrue(тело['db'])
        self.assertTrue(тело['redis_default'])
        self.assertFalse(тело['redis_sessions'])

    def test_наружу_не_утекают_подробности_ошибки(self):
        with mock.patch('config.health.connection') as база:
            база.cursor.side_effect = RuntimeError(
                'connection to server at "10.0.0.5", user "weconomics" failed')
            ответ = self.client.get(reverse('health'))
        тело = ответ.content.decode()
        self.assertNotIn('10.0.0.5', тело)
        self.assertNotIn('weconomics', тело)

    def test_ответ_не_кэшируется(self):
        ответ = self.client.get(reverse('health'))
        self.assertIn('no-cache', ответ.headers.get('Cache-Control', ''))

    def test_не_требует_авторизации(self):
        """Внешний мониторинг не логинится — эндпоинт открыт всем."""
        self.client.logout()
        ответ = self.client.get(reverse('health'))
        self.assertEqual(ответ.status_code, 200)
