# -*- coding: utf-8 -*-
u"""Сервер разработки держит WebSocket: `runserver` — версия daphne (15.09.2026).

С channels 4 приложение `channels` больше не подменяет `runserver`: ASGI-версия
команды живёт в приложении `daphne`, и стоять оно должно выше
`django.contrib.staticfiles` — иначе команду забирает обычный WSGI-сервер
статики. Найдено пятым запуском ночной сессии 15.09.2026: локально сокет лобби
дуэли не открывался, а синхронная дуэль без сокета не начинается вовсе — кнопки
«Играть» у неё нет (ADR 0105).
"""
from django.conf import settings
from django.core.management import get_commands
from django.test import SimpleTestCase


class AsgiRunserverTests(SimpleTestCase):
    def test_runserver_comes_from_daphne(self):
        self.assertEqual(get_commands()['runserver'], 'daphne')

    def test_daphne_stands_above_staticfiles(self):
        apps = list(settings.INSTALLED_APPS)
        self.assertLess(apps.index('daphne'), apps.index('django.contrib.staticfiles'))
