"""Стена 2 тура по дням: сколько дошло, сколько прошло через Telegram и через почту.

    manage.py vp_wall_stats [--days 7]

Нужна для решения «сколько людей уходит через почту» (решение 28.10.2026):
почта — запасной путь, и если через неё идёт заметная доля, это сигнал.
День — день, когда человек ДОШЁЛ до стены (`VPWall.created_at`, местное время):
по каждому дню видно, чем кончилось у тех, кто пришёл в этот день.
«Застрял на контакте» — контакта нет, но есть код привязки или привязка без подписки.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from vp.models import VPTelegramLink, VPTelegramToken, VPWall


def _share(part, whole):
    return '%d (%d%%)' % (part, round(100 * part / whole)) if whole else '0'


class Command(BaseCommand):
    help = 'Стена тренажёра ВП по дням: дошли, Telegram, почта, застряли, анкета.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7)

    def handle(self, *args, **options):
        out = self.stdout.write
        since = timezone.now() - timedelta(days=options['days'])
        rows = list(VPWall.objects.filter(created_at__gte=since).order_by('created_at'))
        users = [row.user_id for row in rows]
        tried = (set(VPTelegramToken.objects.filter(user_id__in=users)
                     .values_list('user_id', flat=True))
                 | set(VPTelegramLink.objects.filter(user_id__in=users)
                       .values_list('user_id', flat=True)))
        by_day = defaultdict(Counter)
        for row in rows:
            day = timezone.localtime(row.created_at).date()
            day_row = by_day[day]
            day_row['wall'] += 1
            day_row[row.contact_via or 'none'] += 1
            if not row.contact_via and row.user_id in tried:
                day_row['stuck'] += 1
            if row.survey_at:
                day_row['survey'] += 1
        out('Стена ВП за %d дн.' % options['days'])
        out('день        дошли  tg        email     застряли  анкета')
        total = Counter()
        for day in sorted(by_day):
            c = by_day[day]
            total.update(c)
            out('%s  %5d  %-8s  %-8s  %8d  %6d' % (
                day, c['wall'], _share(c['tg'], c['wall']), _share(c['email'], c['wall']),
                c['stuck'], c['survey']))
        out('всего       %5d  %-8s  %-8s  %8d  %6d' % (
            total['wall'], _share(total['tg'], total['wall']),
            _share(total['email'], total['wall']), total['stuck'], total['survey']))
        surveyed = [row for row in rows if row.survey_at]
        for field, title in (('grade', 'Класс'), ('tour2_status', 'Прошёл во 2 тур'),
                             ('source', 'Откуда узнал')):
            labels = dict(VPWall._meta.get_field(field).choices)
            counts = Counter(getattr(row, field) for row in surveyed)
            out('%s: %s' % (title, ', '.join(
                '%s – %d' % (labels.get(key, key), n) for key, n in counts.most_common())
                or 'нет ответов'))
