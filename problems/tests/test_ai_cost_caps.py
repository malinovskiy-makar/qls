# -*- coding: utf-8 -*-
"""Суточный денежный потолок у каждой платной работы сайта (24.09.2026).

До этого потолок стоял только у переранжирования поиска и чата; проверка
решения по фото, распознавание вложений и ИИ-сборка домашки тратили без
ограничения. Проверяется ровно главное: потолок ЕСТЬ в боевых настройках
(без `override_settings`), и за ним вызов к поставщику не уходит.
"""
from decimal import Decimal

from django.conf import settings
from django.test import TestCase, override_settings

from problems.ai import core
from problems.models import AiUsageLog

# Все работы, до которых дотягивается сайт (не команды данных).
SITE_KINDS = ('search_rerank', 'catalog_chat', 'catalog_check',
              'catalog_ocr', 'homework_plan')


class CostCapsTests(TestCase):

    def test_every_site_kind_has_a_cap_in_real_settings(self):
        for kind in SITE_KINDS:
            with self.subTest(kind=kind):
                self.assertIn(kind, settings.AI_DAILY_COST_CAPS)
                self.assertGreater(settings.AI_DAILY_COST_CAPS[kind], 0)

    def test_over_the_cap_the_provider_is_not_called(self):
        calls = []

        def fake(system_blocks, user_text):
            calls.append(user_text)
            return '{"text": "ok"}'

        for kind in ('catalog_check', 'catalog_ocr', 'homework_plan'):
            with self.subTest(kind=kind):
                AiUsageLog.objects.create(
                    user=None, kind=kind, model_name='m',
                    cost_usd=Decimal(str(settings.AI_DAILY_COST_CAPS[kind]))
                    + Decimal('0.01'))
                with override_settings(AI_PROVIDER='fake',
                                       AI_FAKE_REPLY=fake):
                    with self.assertRaises(core.AiUnavailable) as caught:
                        core.run(kind, 'текст', {}, None, check_limit=False)
                self.assertEqual(caught.exception.kind, 'limit')
        self.assertEqual(calls, [])
