"""Заливка варианта «Высшей пробы» из YAML: `manage.py import_vp файл.yaml`.

⚠️ ИДЕМПОТЕНТНА: повторный запуск того же файла не плодит дубли и меняет
только отличающиеся поля. Вариант ищется по slug, задание — по паре
(вариант, номер).

⚠️ ИНВАРИАНТЫ ПЕЧАТАЮТСЯ ВСЕГДА, даже при --dry-run и даже при отказе:
число заданий, сумма баллов, разбивка по блокам, разрывы змейки. Разрыв
цепочки по умолчанию — ПРЕДУПРЕЖДЕНИЕ (варианты бывают с настоящими
разрывами), отказ только с --strict-chain.

Вариант заливается ЧЕРНОВИКОМ; опубликовать — ключом --publish.
"""
import pathlib

import yaml
from django.core.management.base import BaseCommand, CommandError

from vp import loader


class Command(BaseCommand):
    help = 'Залить вариант 1 тура «Высшей пробы» из YAML-файла (идемпотентно).'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Путь к YAML-файлу варианта.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Всё посчитать и проверить, в базу не писать.')
        parser.add_argument('--strict-chain', action='store_true',
                            help='Разрыв цепочки змейки — отказ, а не предупреждение.')
        parser.add_argument('--publish', action='store_true',
                            help='Опубликовать вариант (по умолчанию — черновик).')

    def handle(self, *args, **options):
        path = pathlib.Path(options['path'])
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
        except OSError as exc:
            raise CommandError(f'Не удалось прочитать {path}: {exc}')
        except yaml.YAMLError as exc:
            raise CommandError(f'{path}: это не корректный YAML: {exc}')

        parsed = loader.normalize(data)
        breaks = loader.find_chain_breaks(parsed.items)
        self._print_invariants(parsed, breaks)
        for warning in parsed.warnings:
            self.stdout.write(self.style.WARNING(f'  предупреждение: {warning}'))

        errors = list(parsed.errors)
        if options['strict_chain'] and breaks:
            errors.append(f'цепочка змейки разорвана в {len(breaks)} местах '
                          f'(включён --strict-chain)')
        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(f'ОШИБКА: {error}'))
            raise CommandError(
                f'Отказ: ошибок {len(errors)}. Записано: 0. В базе ничего не менялось.')

        try:
            result = loader.write_variant(
                parsed, publish=options['publish'], dry_run=options['dry_run'])
        except loader.StaleItemsError as exc:
            raise CommandError(f'Отказ: {exc} Записано: 0.')
        self._print_result(parsed, result, options['dry_run'])

    def _print_invariants(self, parsed, breaks):
        summary = loader.summarize(parsed.items)
        slug = parsed.variant.get('slug', '?')
        self.stdout.write(f'Вариант: {slug}')
        self.stdout.write(f'Заданий в файле: {summary["count"]}')
        self.stdout.write(f'Сумма баллов: {summary["total"]}')
        self.stdout.write('Блоки (блок · заданий · баллов):')
        for block, (count, total) in summary['blocks'].items():
            self.stdout.write(f'  {block:<9} {count:>3}  {total}')
        if breaks:
            self.stdout.write(self.style.WARNING(
                f'Разрывов цепочки змейки: {len(breaks)}'))
            for line in breaks:
                self.stdout.write(self.style.WARNING(f'  {line}'))
        else:
            self.stdout.write('Разрывов цепочки змейки: 0')

    def _print_result(self, parsed, result, dry_run):
        prefix = '[dry-run, в базу не писали] ' if dry_run else ''
        self.stdout.write(f'{prefix}Заданий записано: {result.saved_items} '
                          f'из {len(parsed.items)} в файле')
        if result.is_noop:
            self.stdout.write(self.style.SUCCESS(
                f'{prefix}Изменений нет: вариант и все {result.unchanged} '
                f'заданий уже совпадают с файлом.'))
            return
        if result.variant_created:
            self.stdout.write(f'{prefix}Вариант создан (черновик, если без --publish).')
        elif result.variant_changed:
            self.stdout.write(f'{prefix}Вариант: изменены поля '
                              f'{", ".join(result.variant_changed)}')
        if result.created:
            self.stdout.write(f'{prefix}Созданы задания: {result.created}')
        for number, fields in sorted(result.updated.items()):
            self.stdout.write(f'{prefix}№{number}: изменены поля {", ".join(fields)}')
        if result.deleted:
            self.stdout.write(f'{prefix}Удалены задания: {result.deleted}')
        self.stdout.write(f'Без изменений заданий: {result.unchanged}')
        if result.has_attempts and (result.updated or result.variant_changed):
            self.stdout.write(self.style.WARNING(
                'У варианта уже есть попытки: правка эталона не пересчитывает '
                'уже сданные ответы.'))
        self.stdout.write(self.style.SUCCESS(f'{prefix}Готово.'))
