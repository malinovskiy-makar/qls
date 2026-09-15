# -*- coding: utf-8 -*-
"""`analytics_export` — события беты в CSV для разбора после беты (15.09.2026).

Плоские колонки плюс `props` JSON-строкой. Кодировка `utf-8-sig`: так таблица
с кириллицей открывается в Excel без ручного выбора кодировки.

Запуск:
    manage.py analytics_export --since 2026-09-15 --out reports/events.csv
    manage.py analytics_export --since 2026-09-15 --until 2026-09-30 --out events.csv
"""
import csv
import json
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from problems.models_platform import Event

COLUMNS = ('ts', 'name', 'page_key', 'path', 'user_id', 'visitor', 'session_key',
           'duration_ms', 'viewport', 'user_agent', 'props')


class Command(BaseCommand):
    help = 'Выгрузить события беты в CSV (props — JSON-строкой).'

    def add_arguments(self, parser):
        parser.add_argument('--since', required=True,
                            help='С даты включительно, ГГГГ-ММ-ДД.')
        parser.add_argument('--until', help='По дату включительно, ГГГГ-ММ-ДД.')
        parser.add_argument('--out', required=True, help='Куда писать CSV.')

    def handle(self, *args, **options):
        events = Event.objects.filter(ts__gte=_day(options['since']))
        if options['until']:
            events = events.filter(ts__lt=_day(options['until']) + timedelta(days=1))
        count = 0
        with open(options['out'], 'w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(COLUMNS)
            for event in events.order_by('ts', 'pk').iterator(chunk_size=2000):
                writer.writerow([_cell(value) for value in (
                    event.ts.isoformat(), event.name, event.page_key, event.path,
                    event.user_id or '', event.visitor, event.session_key,
                    '' if event.duration_ms is None else event.duration_ms,
                    event.viewport, event.user_agent,
                    json.dumps(event.props, ensure_ascii=False))])
                count += 1
        self.stdout.write('Выгружено событий: %d → %s' % (count, options['out']))


#: С этих символов Excel и LibreOffice начинают формулу (OWASP «CSV Injection»).
FORMULA_START = ('=', '+', '-', '@', '\t', '\r')


def _cell(value):
    """Ячейка без формулы. Имя события, путь, браузер и посетителя присылает
    любой, кто достучится до /api/track/, а файл открывают в Excel: ячейка
    `=HYPERLINK(…)` сработала бы у разборщика. Апостроф в начале Excel
    показывает как текст и сам не выводит."""
    text = '' if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text


def _day(text):
    try:
        return timezone.make_aware(datetime.strptime(text, '%Y-%m-%d'))
    except ValueError:
        raise CommandError('Дата %r — не ГГГГ-ММ-ДД.' % text) from None
