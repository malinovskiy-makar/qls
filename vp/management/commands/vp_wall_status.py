"""Состояние стены 2 тура: включена ли, какие пути настроены, сколько людей где.

    manage.py vp_wall_status

⚠️ ЗНАЧЕНИЯ СЕКРЕТОВ НЕ ПЕЧАТАЮТСЯ — только «задан / не задан».
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count

from problems import email_codes
from vp import config, telegram, wall
from vp.models import VPWall


def _set(name):
    return 'задан' if (getattr(settings, name, '') or '').strip() else 'не задан'


class Command(BaseCommand):
    help = 'Стена тренажёра ВП: настройки путей и число людей (без значений секретов).'

    def handle(self, *args, **options):
        out = self.stdout.write
        out('Стена: %s; туры: %s' % ('включена' if wall.enabled() else 'выключена',
                                     ', '.join(map(str, config.WALL_TOURS))))
        out('Путь tg: %s (VP_WALL_TG_ENABLED=%s)' % (
            'да' if telegram.enabled() else 'нет',
            '1' if getattr(settings, 'VP_WALL_TG_ENABLED', True) else '0'))
        for name in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_USERNAME',
                     'TELEGRAM_WEBHOOK_SECRET', 'TELEGRAM_CHANNEL'):
            out('  %s: %s' % (name, _set(name)))
        out('Путь email: %s (MAIL_ENABLED)' % ('да' if email_codes.mail_enabled() else 'нет'))
        rows = dict(VPWall.objects.order_by().values_list('contact_via').annotate(n=Count('id')))
        out('Людей на стене: %d' % sum(rows.values()))
        out('  без контакта: %d; tg: %d; email: %d' % (
            rows.get('', 0), rows.get('tg', 0), rows.get('email', 0)))
        out('  с анкетой: %d' % VPWall.objects.filter(survey_at__isnull=False).count())
