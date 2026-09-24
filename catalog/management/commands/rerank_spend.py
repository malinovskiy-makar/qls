# -*- coding: utf-8 -*-
"""Траты умного поиска по дням — ТОЛЬКО ЧТЕНИЕ (24.09.2026, ADR 0128).

    manage.py rerank_spend            # последние 10 суток
    manage.py rerank_spend --days 30

По строке на московские сутки: вызовов, $, первый и последний вызов и момент,
когда накопленная сумма дошла до потолка (`AI_DAILY_COST_CAPS['search_rerank']`).
Сумма и время — по `AiUsageLog`; в базу команда не пишет ничего.

Зачем владельцу: после выкатки 24.09 увидеть, что потолок больше не
выбирается к утру (17–19.09 — к 20:42, 09:18 и 07:35).
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from problems.ai import core
from problems.models import AiUsageLog

from catalog.rerank import USAGE_KIND


class Command(BaseCommand):
    help = 'Траты переранжирования поиска по дням (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=10)

    def handle(self, *args, **options):
        days = max(1, options['days'])
        cap = core.daily_cost_cap(USAGE_KIND)
        now = timezone.localtime(timezone.now())
        start = (now - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        by_day = {}
        rows = (AiUsageLog.objects.filter(kind=USAGE_KIND, created_at__gte=start)
                .order_by('created_at').values_list('created_at', 'cost_usd'))
        for created, cost in rows:
            moment = timezone.localtime(created)
            by_day.setdefault(moment.date(), []).append((moment, cost or Decimal(0)))

        self.stdout.write('Потолок: $%s в сутки' % (cap if cap is not None else '—'))
        self.stdout.write('%-10s %7s %9s %6s %6s  %s' % (
            'сутки', 'вызовов', '$', 'с', 'по', 'потолок выбран'))
        for offset in range(days):
            day = (start + timedelta(days=offset)).date()
            items = by_day.get(day, [])
            total = Decimal(0)
            hit = ''
            for moment, cost in items:
                total += cost
                if not hit and cap is not None and total >= cap:
                    hit = moment.strftime('%H:%M')
            self.stdout.write('%-10s %7d %9.4f %6s %6s  %s' % (
                day.isoformat(), len(items), total,
                items[0][0].strftime('%H:%M') if items else '—',
                items[-1][0].strftime('%H:%M') if items else '—',
                hit or 'нет'))
