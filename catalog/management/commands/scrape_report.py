# -*- coding: utf-8 -*-
"""Кто сегодня открыл больше всего РАЗНЫХ задач — ТОЛЬКО ЧТЕНИЕ (24.09.2026).

    manage.py scrape_report

Строки — адреса гостей и аккаунты, дошедшие за сутки до 50 разных задач
(`catalog/scrape_guard.py`, ADR 0129): вид, адрес или id аккаунта, число
разных задач и предел. Читает кэш (на бою Redis); в базу не пишет.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from catalog import scrape_guard


class Command(BaseCommand):
    help = 'Топ адресов и аккаунтов по числу разных задач за сегодня (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--top', type=int, default=20)

    def handle(self, *args, **options):
        rows = scrape_guard.today_report()[:max(1, options['top'])]
        if not rows:
            self.stdout.write('Сегодня никто не открыл %d разных задач.' % scrape_guard.REPORT_FROM)
            return
        limits = {'ip': settings.SCRAPE_QUOTA_IP_DAY, 'user': settings.SCRAPE_QUOTA_USER_DAY}
        self.stdout.write('%-5s %-40s %6s %6s' % ('вид', 'адрес / аккаунт', 'задач', 'предел'))
        for kind, ident, count in rows:
            self.stdout.write('%-5s %-40s %6d %6d' % (kind, ident, count, limits.get(kind, 0)))
