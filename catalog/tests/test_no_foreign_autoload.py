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

#: Единственный чужой хост, которому разрешено загружаться САМОМУ, и только после
#: согласия на аналитические cookie (часть Б, 09.10.2026). Список явный: новый
#: хост сюда добавляет владелец, а не тот, кто подключил сервис.
ALLOWED_AFTER_CONSENT = {'mc.yandex.ru'}
METRIKA_ID = '12345678'


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


@override_settings(ALLOWED_HOSTS=list(settings.ALLOWED_HOSTS) + ['testserver'],
                   YANDEX_METRIKA_ID=METRIKA_ID)
class MetrikaAutoloadTests(TestCase):
    """Номер счётчика задан: чужой хост появляется только после согласия.

    Раньше сторож этого не видел вовсе: в тестах номер пуст, и Метрики на
    проверяемых страницах не было (Инвентаризация ПДн 08.10.2026, раздел 3.2).
    """

    @classmethod
    def setUpTestData(cls):
        cls.problem = make_problem()

    def _pages(self):
        return list(AUDIT_PAGES) + [
            ('/catalog/problem/%d/' % self.problem.id, 'страница задачи')]

    def _hosts(self, client):
        found = {}
        for url, label in self._pages():
            html = client.get(url, follow=True).content.decode('utf-8', errors='replace')
            found[label] = {host for host, _u, _k in autoload_hosts(html)}
        return found

    def test_without_consent_there_are_no_foreign_hosts_even_with_a_counter(self):
        for choice in (None, 'necessary'):
            client = Client()
            if choice:
                client.cookies['weco_consent'] = choice
            offenders = {label: hosts for label, hosts in self._hosts(client).items() if hosts}
            self.assertEqual(offenders, {}, 'choice=%s' % choice)

    def test_with_consent_the_only_foreign_host_is_the_allowed_metrika(self):
        client = Client()
        client.cookies['weco_consent'] = 'all'
        found = self._hosts(client)
        union = set().union(*found.values())
        self.assertEqual(union, ALLOWED_AFTER_CONSENT)
        for label, hosts in found.items():
            self.assertTrue(hosts <= ALLOWED_AFTER_CONSENT, label)
