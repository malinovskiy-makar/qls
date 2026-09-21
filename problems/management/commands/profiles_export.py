# -*- coding: utf-8 -*-
"""`profiles_export` — самоотчёт профилей беты в CSV (18.09.2026).

Одна строка на пользователя: признаки человека для разбора событий
`analytics_export` после беты (связываются по `user_id`). Без телефона,
логина, почты и имени — для регрессий они не нужны, а в файле лишние.

Город отдаётся как есть, только `strip().lower()`: отдельного поля «тип
места» нет (решение владельца 18.09), группировку делают в таблице.

Запуск:
    manage.py profiles_export --since 2026-09-18 --out reports/profiles.csv
"""
import csv
from datetime import timedelta

from django.core.management.base import BaseCommand

from problems.management.commands.analytics_export import _cell, _day
from problems.models_platform import UserProfile

COLUMNS = ('user_id', 'date_joined', 'role', 'grade', 'level', 'city', 'school',
           'hours_week', 'source_channel', 'prep_mode', 'olympiad_history', 'goal')
#: Разделитель кодов в ячейке множественного выбора.
LIST_SEP = '|'


class Command(BaseCommand):
    help = 'Выгрузить профили беты в CSV (без телефона, логина, почты, имени).'

    def add_arguments(self, parser):
        parser.add_argument('--since', required=True,
                            help='Зарегистрирован с даты включительно, ГГГГ-ММ-ДД.')
        parser.add_argument('--until', help='По дату включительно, ГГГГ-ММ-ДД.')
        parser.add_argument('--out', required=True, help='Куда писать CSV.')

    def handle(self, *args, **options):
        profiles = (UserProfile.objects.select_related('user')
                    .filter(user__date_joined__gte=_day(options['since'])))
        if options['until']:
            profiles = profiles.filter(
                user__date_joined__lt=_day(options['until']) + timedelta(days=1))
        count = 0
        with open(options['out'], 'w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(COLUMNS)
            for p in profiles.order_by('user__date_joined', 'pk').iterator(chunk_size=2000):
                writer.writerow([_cell(value) for value in (
                    p.user_id, p.user.date_joined.isoformat(), p.role, p.grade,
                    p.level, (p.city or '').strip().lower(), p.school,
                    p.hours_week, p.source_channel,
                    LIST_SEP.join(p.prep_mode or []),
                    LIST_SEP.join(p.olympiad_history or []), p.goal)])
                count += 1
        self.stdout.write('Выгружено профилей: %d → %s' % (count, options['out']))
