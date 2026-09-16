"""Пакет синхронизации банка — ДОМА (ADR 0107).

Пишет `bank_sync_<время>/`: `problems.jsonl` (задача на строку: поля белого
списка, связи и дочерние строки по естественным ключам), `refs.json`
(справочники целиком) и `manifest.json` (формат, HEAD, число задач, хеши).
Базу не меняет. На бою пакет читает `bank_sync_apply`.

    manage.py bank_sync_export                          # видимый каталог, все поля
    manage.py bank_sync_export --fields title           # только заголовки
    manage.py bank_sync_export --ids-file ids.txt --fields tags,topics
"""
import re
# subprocess нужен ровно для одной команды: HEAD репозитория в манифест.
import subprocess  # nosec B404
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems import bank_sync


def _git_head():
    try:
        done = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=settings.BASE_DIR,  # nosec B603 B607
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ''
    return done.stdout.strip()


class Command(BaseCommand):
    help = 'Пакет синхронизации банка дом → бой (только чтение базы).'

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group()
        scope.add_argument('--scope', choices=['catalog'],
                           help='Видимый каталог (так и по умолчанию).')
        scope.add_argument('--ids-file', help='Файл с id задач (любые разделители).')
        parser.add_argument('--fields', default='',
                            help='Через запятую: поля задачи и таблицы (%s). '
                                 'Пусто — весь белый список.' % ', '.join(bank_sync.CHILD_BY_NAME))
        parser.add_argument('--out', default='',
                            help='Каталог пакета (по умолчанию reports/bank_sync/bank_sync_<время>).')

    def handle(self, *args, **options):
        try:
            names = bank_sync.parse_fields(options['fields'])
        except ValueError as exc:
            raise CommandError(exc)
        if options['ids_file']:
            text = Path(options['ids_file']).read_text(encoding='utf-8')
            ids = sorted({int(x) for x in re.findall(r'\d+', text)})
            scope = 'ids-file:%s' % Path(options['ids_file']).name
        else:
            from catalog.filters import base_queryset
            ids = list(base_queryset('catalog').values_list('id', flat=True))
            scope = 'catalog'
        out = Path(options['out'] or Path(settings.BASE_DIR) / 'reports' / 'bank_sync'
                   / ('bank_sync_%s' % datetime.now().strftime('%Y%m%d_%H%M%S')))
        if out.exists():
            raise CommandError('Каталог %s уже есть — пакет не перезаписывается.' % out)
        manifest = bank_sync.export(ids, names, out, scope=scope, head=_git_head())
        self.stdout.write('Пакет: %s' % out)
        self.stdout.write('Задач: %d (охват %s, запрошено id: %d)'
                          % (manifest['problems'], scope, len(ids)))
        self.stdout.write('Справочники: %s' % (manifest['refs'] or 'не нужны'))
        self.stdout.write('Поля: %s' % ', '.join(names))
