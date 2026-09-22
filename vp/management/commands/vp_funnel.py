"""`vp_funnel` — воронка «Высшей пробы»: сколько людей дошло от посадочной до старта и до сдачи.

Читает события беты (`Event`), которые пишет раздел через `/api/track/`; ничего не меняет.

Запуск:
    manage.py vp_funnel
    manage.py vp_funnel --since 2026-09-24
    manage.py vp_funnel --since 2026-09-26 --until 2026-09-30
"""
from datetime import timedelta

from django.core.management.base import BaseCommand

from problems.management.commands.analytics_export import _day
from vp.funnel import funnel


def _share(part, whole):
    return '%d %%' % round(100 * part / whole) if whole else '–'


class Command(BaseCommand):
    help = 'Воронка ВП по событиям аналитики: посадочная → старт → сдача (люди, не события).'

    def add_arguments(self, parser):
        parser.add_argument('--since', help='С даты включительно, ГГГГ-ММ-ДД.')
        parser.add_argument('--until', help='По дату включительно, ГГГГ-ММ-ДД.')

    def handle(self, *args, **options):
        since = _day(options['since']) if options['since'] else None
        until = _day(options['until']) + timedelta(days=1) if options['until'] else None
        data = funnel(since, until)
        out = self.stdout.write
        out('Открыли посадочную:        %d' % data['landing'])
        out('Начали вариант:            %d  (из открывших посадочную: %d, %s)' % (
            data['start'], data['landing_and_start'],
            _share(data['landing_and_start'], data['landing'])))
        out('Сдали вариант:             %d  (из начавших: %d, %s)' % (
            data['submit'], data['start_and_submit'],
            _share(data['start_and_submit'], data['start'])))
        out('Люди считаются по cookie посетителя: один браузер – один человек.')
