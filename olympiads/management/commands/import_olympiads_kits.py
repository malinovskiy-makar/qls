"""Импорт комплектов из пакета олимпиад: комплекты, классы, файлы, счётчики.

    manage.py import_olympiads_kits <папка пакета>              # сухой прогон
    manage.py import_olympiads_kits <папка пакета> --apply      # запись
    manage.py import_olympiads_kits <папка пакета> --apply --files

⚠️ ПО УМОЛЧАНИЮ — СУХОЙ ПРОГОН. Он выполняет всю работу в транзакции и
откатывает её: числа в отчёте настоящие, а в базе после него ничего нет.
Запись — только с `--apply`, копирование PDF — только с `--files`.

⚠️ В банк задач (`Problem`) команда не пишет ничего; позиций комплектов
(`OlympiadVariantItem`) не создаёт — у них `problem` обязателен. Логика и
причины — в `olympiads/kits_import.py`.
"""
import datetime
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from olympiads import kits_import as ki


class Command(BaseCommand):
    help = ('Импорт комплектов пакета олимпиад. Без --apply — сухой прогон '
            '(в базе ничего не остаётся).')

    def add_arguments(self, parser):
        parser.add_argument('package', help='Папка пакета (где лежат */kits/).')
        parser.add_argument('--only', default='',
                            help='Только один слаг, например vseros.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Сухой прогон (по умолчанию и так он).')
        parser.add_argument('--apply', action='store_true',
                            help='Записать в базу.')
        parser.add_argument('--hide-legacy-kits', action='store_true',
                            help='Скрыть прежние комплекты без kit_key '
                                 '(ничего не удаляет). В сухом прогоне '
                                 'только показывает.')
        parser.add_argument('--files', action='store_true',
                            help='Скопировать PDF в MEDIA_ROOT (с --apply; '
                                 'без него — только проверка).')

    def handle(self, *args, **options):
        if options['dry_run'] and options['apply']:
            raise CommandError('--dry-run и --apply вместе нельзя.')
        apply = options['apply']
        root = os.path.abspath(options['package'])
        kits = ki.read_package(root, options['only'])
        report = ki.Report()
        report.summary_package = ki.package_summary(kits)
        importer = ki.KitImporter(report)
        slugs = sorted({data['olympiad']['slug'] for _, data in kits})

        # Всё в одной внешней транзакции: сухой прогон откатывает её целиком,
        # а запись держится на транзакциях комплектов внутри (savepoint'ы).
        with transaction.atomic():
            overlaps = ki.existing_overlaps(kits)
            for _, data in kits:
                importer.import_kit(data)
            ki.mark_absent([d['kit_id'] for _, d in kits], slugs, report)
            report.summary_db = ki.database_summary(
                [d['kit_id'] for _, d in kits])
            if options['hide_legacy_kits']:
                ki.hide_legacy_kits(report)
            if options['files']:
                ki.copy_files(kits, root, str(settings.MEDIA_ROOT), report,
                              apply)
            if not apply:
                transaction.set_rollback(True)

        self._print(report, overlaps, apply, len(kits))
        path = self._write_report(report, overlaps, apply, root)
        self.stdout.write('Отчёт: {}'.format(path))

    def _print(self, report, overlaps, apply, total):
        mode = 'ЗАПИСАНО' if apply else 'СУХОЙ ПРОГОН (в базе ничего не осталось)'
        self.stdout.write(self.style.SUCCESS(
            '{}: комплектов в пакете {}'.format(mode, total)))
        for name, n in sorted(report.counts.items()):
            self.stdout.write('  {:<28} {}'.format(name, n))
        self.stdout.write('Сверка (пакет по файлам | база после записи):')
        for name, value in report.summary_package.items():
            self.stdout.write('  {:<34} {:>7} | {}'.format(
                name, value, report.summary_db.get(name, '—')))
        for name, value in report.summary_db.items():
            if name not in report.summary_package:
                self.stdout.write('  {:<34} {:>7} | {}'.format(
                    name, '—', value))
        for key in ('olympiads_created', 'stages_created',
                    'placeholder_cleared', 'hidden_kits', 'absent_kits'):
            if report.lists[key]:
                self.stdout.write('  {}: {}'.format(
                    key, ', '.join(report.lists[key])))
        for line in report.lists['errors'][:20]:
            self.stdout.write(self.style.WARNING('  ' + line))
        if report.lists['legacy_kits']:
            self.stdout.write('Прежние комплекты (без kit_key) — скрыты{}:'.format(
                '' if apply else ' (только показ, ничего не записано)'))
            for row in report.lists['legacy_kits']:
                self.stdout.write('  #{id} {name} кл.{grade} {ref_event_id}'
                                  .format(**row))
        elif overlaps:
            self.stdout.write('Прежние комплекты (без kit_key), НЕ тронуты:')
            for row in overlaps:
                self.stdout.write(
                    '  #{id} {olympiad} {year} {stage} кл.{grade} '
                    'попыток {attempts} → в пакете {n} шт.'.format(
                        n=len(row['package_kits']), **row))

    def _write_report(self, report, overlaps, apply, root):
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        directory = os.path.join(settings.BASE_DIR, 'reports')
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, 'olympiads_kits_{}.json'.format(stamp))
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'package': root, 'applied': apply,
                       **report.as_dict(), 'existing_overlaps': overlaps},
                      fh, ensure_ascii=False, indent=1)
        return path
