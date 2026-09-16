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
    manage.py bank_sync_apply --revert DIR/apply_<время>/snapshot.json

Повторный `--apply` того же пакета обязан дать 0 изменений.
"""
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from problems import bank_sync


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
            return self._revert(Path(options['revert']))
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
            self._invalidate_search()
        mode = 'запись (--apply)' if options['apply'] else 'сухой прогон'
        lines = bank_sync.report_lines(result, package, mode, names, manifest['problems'],
                                       snapshot=snapshot)
        (report_dir / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        (report_dir / 'changed_ids.txt').write_text(
            '\n'.join(map(str, bank_sync.changed_ids(result))) + '\n', encoding='utf-8')
        self._summary(result, report_dir, snapshot, mode)

    def _summary(self, result, report_dir, snapshot, mode):
        out = self.stdout.write
        out('Режим: %s' % mode)
        out('Задач с изменениями: %d; нет в базе: %d; пропусков: %d'
            % (len(bank_sync.changed_ids(result)), len(result['missing']), len(result['skipped'])))
        for name, ops in result['refs'].items():
            out('  справочник %s: создать %d, обновить %d' % (name, len(ops['create']), len(ops['update'])))
        fields = {}
        for item in result['problems']:
            for f in item['new']:
                fields[f] = fields.get(f, 0) + 1
        for f, n in sorted(fields.items()):
            out('  поле %s: %d' % (f, n))
        for name, ops in result['children'].items():
            if any(ops.values()):
                out('  %s: добавить %d, обновить %d, удалить %d, не удалено %d'
                    % (name, len(ops['create']), len(ops['update']), len(ops['delete']), len(ops['kept'])))
        if bank_sync.is_empty(result):
            out('Изменений нет.')
        out('Отчёт: %s' % (report_dir / 'REPORT.md'))
        if snapshot:
            out('Снимок для отката: %s' % snapshot)

    def _revert(self, path):
        try:
            stats, conflicts = bank_sync.revert(path)
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(exc)
        self._invalidate_search()
        for key, n in sorted(stats.items()):
            self.stdout.write('  %s: %d' % (key, n))
        lines = ['# Откат синхронизации банка', '', '- Снимок: `%s`' % path, '']
        lines += ['- %s: %d' % (k, n) for k, n in sorted(stats.items())]
        if conflicts:
            lines += ['', '## Не возвращено (изменено после синхронизации)', '',
                      '| таблица | где | причина |', '|---|---|---|']
            lines += ['| %s | %s | %s |' % c for c in conflicts]
        report = path.with_name(path.stem + '_REVERT.md')
        report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write('Конфликтов: %d. Отчёт: %s' % (len(conflicts), report))

    def _invalidate_search(self):
        """Тексты и связи изменились — корпус умного поиска и смысловой индекс
        перестраиваются по следующему запросу во ВСЕХ воркерах."""
        try:
            from catalog import rerank, semantic
            rerank.invalidate_corpus()
            semantic.invalidate_index()
        except Exception as exc:  # noqa: BLE001 — поиск не должен ронять синхронизацию
            self.stderr.write('Кэш поиска не сброшен: %s' % exc)
