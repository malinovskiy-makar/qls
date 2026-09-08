# -*- coding: utf-8 -*-
"""Плашка окружения: где мы находимся — на бою или на площадке разработчиков.

⚠️ ЗАЧЕМ ЭТО ВООБЩЕ НУЖНО. 06.09.2026 при выкатке на прод всплыли два бага,
которых не могло быть ни локально, ни в тестах: `settings_production.py` без
`site_meta` (пустое меню) и `varchar(300)` на PostgreSQL. Оба — «прошло на
компьютере разработки, упало на бою». Лекарство — площадка `dev.weconomics.ai`
с БОЕВЫМИ настройками, куда `main` выкатывается сам после зелёного CI. А раз
площадка выглядит как бой во всём, кроме адреса, — человек обязан видеть
глазами, куда именно он смотрит, иначе разбор бага пойдёт не по тому сайту.

⚠️ ПЛАШКУ РИСУЕТ ТОЛЬКО `SITE_ENV=dev`, И ЭТО ГЛАВНОЕ В НАБОРЕ. Значение по
умолчанию — `prod`, то есть на бою правка не меняет ни байта разметки.
Проверка «без переменной плашки нет» здесь не украшение: она сторожит ровно
то, что нельзя сломать.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

import config.context_processors as cp
from django.conf import settings


def _meta(**over):
    """`site_meta` на пустом запросе — нас интересуют только две строки."""
    from django.test import RequestFactory

    request = RequestFactory().get('/')
    request.user = None
    with override_settings(**over):
        return cp.site_meta(request)


class SiteEnvDefaultTests(TestCase):
    """Без переменных окружения сайт считает себя боевым."""

    def test_настройки_по_умолчанию_боевые(self):
        # Читаем то, что реально собралось при импорте settings.py — без
        # SITE_ENV и GIT_SHA в окружении прогона.
        self.assertEqual(settings.SITE_ENV, 'prod')
        self.assertEqual(settings.SITE_BUILD, '')

    def test_site_meta_отдаёт_prod_и_пустую_сборку(self):
        данные = _meta(SITE_ENV='prod', SITE_BUILD='')
        self.assertEqual(данные['site_env'], 'prod')
        self.assertEqual(данные['site_build'], '')


class SiteEnvDevTests(TestCase):
    """При `SITE_ENV=dev` в контексте появляются окружение и хеш сборки."""

    def test_site_meta_отдаёт_dev_и_семь_знаков_хеша(self):
        данные = _meta(SITE_ENV='dev', SITE_BUILD='abcdef0')
        self.assertEqual(данные['site_env'], 'dev')
        self.assertEqual(данные['site_build'], 'abcdef0')

    def test_хеш_режется_до_семи_знаков_настройками(self):
        """`GIT_SHA` приезжает полным (40 знаков) — в шапке нужен короткий.

        Режет именно `settings.py`, а не шаблон: подрезка в разметке
        означала бы её повторение в каждом месте, где хеш понадобится.
        """
        import importlib
        import os

        старое = dict(os.environ)
        os.environ['SITE_ENV'] = 'dev'
        os.environ['GIT_SHA'] = 'abcdef0123456789abcdef0123456789abcdef01'
        try:
            модуль = importlib.import_module('config.settings')
            importlib.reload(модуль)
            self.assertEqual(модуль.SITE_ENV, 'dev')
            self.assertEqual(модуль.SITE_BUILD, 'abcdef0')
        finally:
            os.environ.clear()
            os.environ.update(старое)
            importlib.reload(importlib.import_module('config.settings'))


class SiteEnvRenderTests(TestCase):
    """Плашка на настоящей странице: есть при dev, отсутствует при prod."""

    # Текст плашки. Держим здесь строкой, а не собираем из настроек:
    # тест обязан сломаться, если формулировку поменяют молча.
    ТЕКСТ = 'рабочая версия'

    def test_на_бою_плашки_нет(self):
        with override_settings(SITE_ENV='prod', SITE_BUILD=''):
            ответ = self.client.get('/catalog/')
        self.assertEqual(ответ.status_code, 200)
        self.assertNotContains(ответ, self.ТЕКСТ)
        self.assertNotContains(ответ, 'site-env-strip')

    def test_на_площадке_плашка_есть_и_показывает_хеш(self):
        with override_settings(SITE_ENV='dev', SITE_BUILD='abcdef0'):
            ответ = self.client.get('/catalog/')
        self.assertEqual(ответ.status_code, 200)
        self.assertContains(ответ, self.ТЕКСТ)
        self.assertContains(ответ, 'abcdef0')

    def test_плашка_без_жёстко_вписанных_цветов(self):
        """Цвета — только токенами: сторож канона не должен покраснеть.

        ⚠️ Проверяем ИМЕННО отрисованную плашку, а не файл шаблона: hex мог
        бы приехать из подключённого стиля, и проверка по файлу его бы
        не увидела.
        """
        import re

        with override_settings(SITE_ENV='dev', SITE_BUILD='abcdef0'):
            ответ = self.client.get('/catalog/')
        html = ответ.content.decode()
        начало = html.find('site-env-strip')
        self.assertNotEqual(начало, -1, 'плашки нет в разметке')
        # Берём кусок вокруг плашки вместе с её правилами стиля.
        кусок = html[max(0, начало - 1200):начало + 1200]
        self.assertFalse(re.search(r'#[0-9a-fA-F]{3,8}\b', кусок),
                         'в плашке жёстко вписан цвет — нужны токены')
