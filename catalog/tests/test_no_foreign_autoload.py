# -*- coding: utf-8 -*-
"""Сторож РКН: страница не должна САМА тянуть ресурс с чужого хоста.

Аудит «Аудит зарубежных обращений перед подачей уведомления в РКН»
(Notion-штаб, 2026-09-09) проверил ключевые страницы вручную и не нашёл
автозагрузки внешних хостов — этот тест держит найденный ноль как границу
на будущее. Белый список — ТОЛЬКО собственный домен: пока владелец не
согласовал ни одного стороннего (в т.ч. российского) сервиса на автозагрузку,
любой новый `<script src>`/`<link href>`/`<img src>` на чужой хост роняет
тест, а не проезжает молча до следующего аудита перед подачей уведомления.

Обычная гиперссылка `<a href="https://…">` (пользователь кликает сам) —
НЕ автозагрузка и тест не трогает; см. `problems/audit_html.py`.
"""
from django.conf import settings
from django.test import Client, TestCase, override_settings

from problems.audit_html import AUDIT_PAGES, autoload_hosts
from problems.models import Problem
from problems.tests.factories import make_problem


@override_settings(ALLOWED_HOSTS=list(settings.ALLOWED_HOSTS) + ['testserver'])
class NoForeignAutoloadTests(TestCase):
    """Ни одна из ключевых страниц не должна автозагружать чужой хост."""

    @classmethod
    def setUpTestData(cls):
        cls.problem = make_problem()

    def test_public_pages_have_no_foreign_autoload(self):
        client = Client()
        pages = list(AUDIT_PAGES) + [
            ('/catalog/problem/%d/' % self.problem.id, 'страница задачи'),
        ]
        offenders = []
        for url, label in pages:
            resp = client.get(url, follow=True)
            html = resp.content.decode('utf-8', errors='replace')
            found = autoload_hosts(html)
            if found:
                offenders.append((label, url, found))

        self.assertFalse(
            offenders,
            'Автозагрузка с чужого хоста найдена там, где её не должно '
            'быть (для РКН это трансграничная передача): %r' % (offenders,))
