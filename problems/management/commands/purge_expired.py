# -*- coding: utf-8 -*-
"""Сроки хранения данных (Политика, раздел 7; часть Б правового контура, 09.10.2026).

    manage.py purge_expired             # сухой прогон: числа по всем пунктам
    manage.py purge_expired --apply     # удалить

Удаляет старше `DATA_RETENTION_MONTHS` (12): реплики и вложения чата, загруженные
файлы, события, журнал поиска, обращения со снимками, жалобы; у сдач стирает файл.
Дополнительно вызывает `clearsessions` и `cleanup_training_attempts` (гостевые
попытки тренировки). Аккаунты без входа больше 3 лет только перечисляются числом.

Запускается еженедельно таймером `deploy/systemd/weconomics-purge.timer`; включение –
`docs/SERVER.md`, «Сроки хранения данных».
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand

from problems import retention


class Command(BaseCommand):
    help = 'Удалить данные старше срока хранения (по умолчанию – сухой прогон).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='действительно удалить (без флага – только показать)')

    def handle(self, *args, **options):
        w = self.stdout.write
        if not options['apply']:
            plan = retention.plan()
            w('Сухой прогон. Граница: старше %s (срок хранения %s мес.)'
              % (plan['cutoff'].strftime('%Y-%m-%d'), retention.settings.DATA_RETENTION_MONTHS))
            w('\nСтроки:')
            for label, n in plan['rows'].items():
                w('  %-40s %d' % (label, n))
            w('\nФайлы:')
            for kind, n in plan['files'].items():
                w('  %-40s %d' % (kind, n))
            w('\nПросроченных сессий (clearsessions): %d' % plan['expired_sessions'])
            sink = StringIO()
            call_command('cleanup_training_attempts', '--dry-run', stdout=sink)
            w('Гостевые попытки тренировки: %s' % sink.getvalue().strip())
            w('Аккаунтов без входа больше %d лет (только перечисляются, не удаляются): %d'
              % (retention.INACTIVE_ACCOUNT_YEARS, plan['inactive_accounts']))
            w('\nСухой прогон: ничего не удалено. Для удаления добавьте --apply.')
            return
        result = retention.purge()
        w('Граница: старше %s' % result['cutoff'].strftime('%Y-%m-%d'))
        for label, n in result['rows'].items():
            w('  %-40s %d' % (label, n))
        w('Файлов удалено: %(files_deleted)d (не найдено %(files_missing)d, ошибок %(files_failed)d)'
          % result)
        call_command('clearsessions')
        w('clearsessions выполнен.')
        sink = StringIO()
        call_command('cleanup_training_attempts', stdout=sink)
        w('Гостевые попытки тренировки: %s' % sink.getvalue().strip())
        w('Аккаунтов без входа больше %d лет (не удаляются): %d'
          % (retention.INACTIVE_ACCOUNT_YEARS, retention.inactive_accounts()))
