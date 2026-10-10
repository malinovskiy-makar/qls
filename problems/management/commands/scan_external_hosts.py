# -*- coding: utf-8 -*-
"""Аудит РКН (фаза 2): найти автозагрузку внешних хостов на ключевых страницах.

Рендерит страницы из `problems.audit_html.AUDIT_PAGES` через Django test
client, плюс страницу задачи и кабинеты преподавателя/ученика (если в базе
есть подходящие пользователи), и печатает по каждой странице список внешних
хостов с автозагрузкой. Обычные гиперссылки `<a href>` печатаются отдельно
и на вердикт не влияют — см. `problems/audit_html.py`.

    manage.py scan_external_hosts
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.test import Client

from problems.audit_html import AUDIT_PAGES, autoload_hosts, hyperlinks
from problems.models import Problem, User


class Command(BaseCommand):
    help = 'Аудит РКН: ищет автозагрузку внешних хостов на ключевых страницах.'

    def handle(self, *args, **options):
        # ALLOWED_HOSTS у dev-настроек пуст — test client стучится как
        # 'testserver', его нужно временно разрешить только для этого прогона.
        original_hosts = settings.ALLOWED_HOSTS
        settings.ALLOWED_HOSTS = list(original_hosts) + ['testserver']
        try:
            self._run()
        finally:
            settings.ALLOWED_HOSTS = original_hosts

    def _run(self):
        client = Client()
        pages = list(AUDIT_PAGES)

        problem = (Problem.objects.filter(
            status='published', hidden_pending_review=False).first()
            or Problem.objects.first())
        if problem is not None:
            pages.append(('/catalog/problem/%d/' % problem.id, 'страница задачи'))

        total_autoload = 0
        seen_hosts = set()

        for url, label in pages:
            resp = client.get(url, follow=True)
            html = resp.content.decode('utf-8', errors='replace')
            auto = autoload_hosts(html)
            links = hyperlinks(html)
            total_autoload += len(auto)
            seen_hosts.update(h for h, u, k in auto)
            self._report(label, url, resp.status_code, auto, links)

        teacher = User.objects.filter(role='teacher').first()
        if teacher is not None:
            c = Client()
            c.force_login(teacher)
            resp = c.get('/teacher/', follow=True)
            html = resp.content.decode('utf-8', errors='replace')
            auto = autoload_hosts(html)
            links = hyperlinks(html)
            total_autoload += len(auto)
            seen_hosts.update(h for h, u, k in auto)
            self._report('кабинет преподавателя', '/teacher/', resp.status_code,
                         auto, links)
        else:
            self.stdout.write('кабинет преподавателя: нет пользователя role=teacher в базе')

        student = User.objects.filter(role='student').first()
        if student is not None:
            c = Client()
            c.force_login(student)
            resp = c.get('/student/', follow=True)
            html = resp.content.decode('utf-8', errors='replace')
            auto = autoload_hosts(html)
            links = hyperlinks(html)
            total_autoload += len(auto)
            seen_hosts.update(h for h, u, k in auto)
            self._report('кабинет ученика', '/student/', resp.status_code,
                         auto, links)
        else:
            self.stdout.write('кабинет ученика: нет пользователя role=student в базе')

        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(
            'ИТОГО: %d автозагрузок с внешних хостов, уникальных хостов: %d (%s)'
            % (total_autoload, len(seen_hosts), ', '.join(sorted(seen_hosts)) or '—'))

    def _report(self, label, url, status, auto, links):
        self.stdout.write('')
        self.stdout.write('--- %s (%s, HTTP %s) ---' % (label, url, status))
        if not auto:
            self.stdout.write('  автозагрузка с внешних хостов: 0')
        for host, u, kind in auto:
            self.stdout.write('  АВТОЗАГРУЗКА: %s  [%s]  %s' % (host, kind, u))
        for host, u in links:
            self.stdout.write('  ссылка (не автозагрузка): %s  %s' % (host, u))
