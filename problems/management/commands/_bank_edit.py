"""Общая основа правок банка дома на движке синхронизации (ADR 0107).

Команда строит план в формате `problems.bank_sync.plan` — какие поля задач,
строки связей и справочники поменять, — а запись, снимок и откат делает
движок: у всех правок одинаково проверенные `--apply` и `--revert`.
Модуль начинается с подчёркивания — Django не считает его командой.
"""
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems import bank_sync


def invalidate_search(stderr):
    """Тексты и связи изменились — корпус умного поиска и смысловой индекс
    перестраиваются по следующему запросу во ВСЕХ воркерах."""
    try:
        from catalog import rerank, semantic
        rerank.invalidate_corpus()
        semantic.invalidate_index()
    except Exception as exc:  # noqa: BLE001 — поиск не должен ронять правку
        stderr.write('Кэш поиска не сброшен: %s' % exc)


def revert_and_report(path, stdout, stderr):
    try:
        stats, conflicts = bank_sync.revert(path)
    except (OSError, ValueError, KeyError) as exc:
        raise CommandError(exc)
    invalidate_search(stderr)
    for key, n in sorted(stats.items()):
        stdout.write('  %s: %d' % (key, n))
    lines = ['# Откат', '', '- Снимок: `%s`' % path, '']
    lines += ['- %s: %d' % (k, n) for k, n in sorted(stats.items())]
    if conflicts:
        lines += ['', '## Не возвращено (изменено после записи)', '',
                  '| таблица | где | причина |', '|---|---|---|']
        lines += ['| %s | %s | %s |' % conflict for conflict in conflicts]
    report = path.with_name(path.stem + '_REVERT.md')
    report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    stdout.write('Конфликтов: %d. Отчёт: %s' % (len(conflicts), report))


def summary(result, stdout):
    stdout.write('Задач с изменениями: %d; пропусков: %d'
                 % (len(bank_sync.changed_ids(result)), len(result['skipped'])))
    for name, ops in result['refs'].items():
        if ops['create'] or ops['update']:
            stdout.write('  справочник %s: создать %d, обновить %d'
                         % (name, len(ops['create']), len(ops['update'])))
    fields = {}
    for item in result['problems']:
        for f in item['new']:
            fields[f] = fields.get(f, 0) + 1
    for f, n in sorted(fields.items()):
        stdout.write('  поле %s: %d' % (f, n))
    for name, ops in result['children'].items():
        if any(ops.values()):
            stdout.write('  %s: добавить %d, обновить %d, удалить %d, не удалено %d'
                         % (name, len(ops['create']), len(ops['update']),
                            len(ops['delete']), len(ops['kept'])))
    if bank_sync.is_empty(result):
        stdout.write('Изменений нет.')


class BankEditCommand(BaseCommand):
    """Сухой прогон по умолчанию, `--apply` со снимком, `--revert` по снимку.

    Наследник задаёт `build()` → (план, строки шапки отчёта, доп. строки)."""

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true', help='Только отчёт (так и по умолчанию).')
        mode.add_argument('--apply', action='store_true', help='Записать одной транзакцией со снимком.')
        mode.add_argument('--revert', metavar='SNAPSHOT', help='Откатить по снимку прошлого --apply.')
        parser.add_argument('--report', default='',
                            help='Каталог отчёта и снимка (по умолчанию reports/bank_edits/<команда>).')

    def build(self, options):
        raise NotImplementedError

    def handle(self, *args, **options):
        if options['revert']:
            return revert_and_report(Path(options['revert']), self.stdout, self.stderr)
        name = self.__module__.rsplit('.', 1)[-1]
        report_dir = Path(options['report'] or Path(settings.BASE_DIR) / 'reports' / 'bank_edits' / name)
        report_dir.mkdir(parents=True, exist_ok=True)
        result, header, extra = self.build(options)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        snapshot = None
        if options['apply'] and not bank_sync.is_empty(result):
            snapshot = report_dir / ('snapshot_%s.json' % stamp)
            names = list(result['children']) or ['fields']
            bank_sync.execute(result, names, name, snapshot)
            invalidate_search(self.stderr)
        mode = 'запись (--apply)' if options['apply'] else 'сухой прогон'
        lines = ['# %s — %s' % (name, mode), ''] + header + ['']
        lines += bank_sync.report_lines(result, snapshot=snapshot) + [''] + extra
        (report_dir / ('REPORT_%s.md' % stamp)).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write('Режим: %s' % mode)
        for line in header:
            self.stdout.write(line)
        summary(result, self.stdout)
        self.stdout.write('Отчёт: %s' % (report_dir / ('REPORT_%s.md' % stamp)))
        if snapshot:
            self.stdout.write('Снимок для отката: %s' % snapshot)
