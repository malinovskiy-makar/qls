# -*- coding: utf-8 -*-
"""`search_export` — журнал поиска каталога в CSV (18.09.2026, ADR 0117).

Тот самый файл, по которому после беты оценивается качество поиска: текст
запроса, статус умного поиска, сколько думали, сколько нашли, оценка
человека с комментарием и номера первых выданных задач (через `|`).

Запуск:
    manage.py search_export --since 2026-09-18 --out reports/search.csv
"""
import csv
from datetime import timedelta

from django.core.management.base import BaseCommand

from problems.management.commands.analytics_export import _cell, _day
from problems.models_platform import SearchLog

COLUMNS = ('ts', 'user_id', 'visitor', 'query', 'status', 'ms', 'total',
           'degraded', 'rating', 'rated_at', 'rating_text', 'top_ids')
LIST_SEP = '|'


class Command(BaseCommand):
    help = 'Выгрузить журнал поиска каталога в CSV.'

    def add_arguments(self, parser):
        parser.add_argument('--since', required=True,
                            help='С даты включительно, ГГГГ-ММ-ДД.')
        parser.add_argument('--until', help='По дату включительно, ГГГГ-ММ-ДД.')
        parser.add_argument('--out', required=True, help='Куда писать CSV.')

    def handle(self, *args, **options):
        rows = SearchLog.objects.filter(ts__gte=_day(options['since']))
        if options['until']:
            rows = rows.filter(ts__lt=_day(options['until']) + timedelta(days=1))
        count = 0
        with open(options['out'], 'w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(COLUMNS)
            for row in rows.order_by('ts', 'pk').iterator(chunk_size=2000):
                writer.writerow([_cell(value) for value in (
                    row.ts.isoformat(), row.user_id or '', row.visitor, row.query,
                    row.status, '' if row.ms is None else row.ms, row.total,
                    int(row.degraded), row.rating,
                    row.rated_at.isoformat() if row.rated_at else '',
                    row.rating_text, LIST_SEP.join(str(i) for i in row.top_ids or []))])
                count += 1
        self.stdout.write('Выгружено запросов: %d → %s' % (count, options['out']))
