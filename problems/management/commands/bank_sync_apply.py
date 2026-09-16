"""Применение пакета синхронизации банка — НА БОЮ и на копии боя (ADR 0107).

Сверяет пакет `bank_sync_export` с базой и меняет только отличающееся:

1. справочники — обновить или создать по естественному ключу (не удаляются);
2. поля задач — `bulk_update` только там, где значение другое;
3. связи и дочерние строки — множество на бою становится равным пакету;
   подпункт, на который что-то ссылается (ответы учеников, черновики…), не
   удаляется, а называется в отчёте.

Задачи, которых нет в базе, не создаются; задачи базы вне пакета не
трогаются. Всё — одной транзакцией, снимок пишется внутри неё.

    manage.py bank_sync_apply --package DIR                 # сухой прогон (по умолчанию)
    manage.py bank_sync_apply --package DIR --apply         # запись + снимок
    manage.py bank_sync_apply --package DIR --fields title  # сузить
    manage.py bank_sync_apply --revert DIR/apply_<время>/snapshot_<время>.json

Повторный `--apply` того же пакета обязан дать 0 изменений.
"""
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from problems import bank_sync
from problems.management.commands._bank_edit import (invalidate_search, revert_and_report,
                                                     summary)


class Command(BaseCommand):
    help = 'Синхронизация банка: применить пакет обновлением (сухой прогон по умолчанию).'

    def add_arguments(self, parser):
        parser.add_argument('--package', help='Каталог пакета bank_sync_export.')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true',
                          help='Только отчёт (так и по умолчанию).')
        mode.add_argument('--apply', action='store_true',
                          help='Записать одной транзакцией со снимком.')
        mode.add_argument('--revert', metavar='SNAPSHOT', help='Откатить по снимку.')
        parser.add_argument('--fields', default='', help='Сузить: поля и таблицы через запятую.')
        parser.add_argument('--report', default='',
                            help='Куда писать REPORT.md и снимок (по умолчанию <пакет>/apply_<время>).')

    def handle(self, *args, **options):
        if options['revert']:
            return revert_and_report(Path(options['revert']), self.stdout, self.stderr)
        if not options['package']:
            raise CommandError('Нужен --package (или --revert).')
        package = Path(options['package'])
        try:
            manifest = bank_sync.read_manifest(package)
            names = [n for n in bank_sync.parse_fields(options['fields'])
                     if n in manifest['fields']]
        except (OSError, ValueError) as exc:
            raise CommandError(exc)
        if not names:
            raise CommandError('Ни одного из запрошенных полей нет в пакете.')

        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_dir = Path(options['report'] or package / ('apply_%s' % stamp))
        report_dir.mkdir(parents=True, exist_ok=True)
        result = bank_sync.plan(package, names)
        snapshot = None
        if options['apply'] and not bank_sync.is_empty(result):
            snapshot = report_dir / ('snapshot_%s.json' % stamp)
            bank_sync.execute(result, names, package, snapshot)
            invalidate_search(self.stderr)
        mode = 'запись (--apply)' if options['apply'] else 'сухой прогон'
        header = ['# Синхронизация банка — %s' % mode, '',
                  '- Пакет: `%s` (HEAD %s, собран %s)' % (package, manifest['git_head'][:8],
                                                         manifest['created_at']),
                  '- Поля: %s' % ', '.join(names),
                  '- Задач в пакете: %d; нет в базе: %d' % (manifest['problems'], len(result['missing'])),
                  '']
        lines = header + bank_sync.report_lines(result, snapshot=snapshot)
        (report_dir / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        (report_dir / 'changed_ids.txt').write_text(
            '\n'.join(map(str, bank_sync.changed_ids(result))) + '\n', encoding='utf-8')
        self.stdout.write('Режим: %s' % mode)
        self.stdout.write('Задач в пакете: %d; нет в базе: %d'
                          % (manifest['problems'], len(result['missing'])))
        summary(result, self.stdout)
        self.stdout.write('Отчёт: %s' % (report_dir / 'REPORT.md'))
        if snapshot:
            self.stdout.write('Снимок для отката: %s' % snapshot)
