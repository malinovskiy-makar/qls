# -*- coding: utf-8 -*-
"""Залить справочник школ для подсказок онбординга (раунд 2, 30.10.2026).

    manage.py load_schools <файл.csv>            # сухой прогон: только счётчики
    manage.py load_schools <файл.csv> --apply    # записать
    manage.py load_schools --format raoo <файл.zip|.xml> [--apply]   # реестр Рособрнадзора

Формат `raoo` (раунд 3, 29.10.2026) — выгрузка реестра аккредитованных организаций
как есть (ZIP или XML внутри). Тот же разборщик и тот же движок, что у
`manage.py sync_schools` (`problems/school_registry.py`, `problems/school_sync.py`):
ключ — идентификатор организации в реестре, исчезнувшие выключаются, а не удаляются.

Файл — CSV в UTF-8 с заголовком. Обязательны `name` и `city`; по желанию
`short_name`, `number`, `kind` (например «ГБОУ»), `region`. Номер, если колонки нет
или она пуста, берётся из названия («Школа № 57» → 57). Как получить такой файл из
государственного реестра аккредитованных организаций — `problems/data/README.md`.

⚠️ ИДЕМПОТЕНТНО: ключ строки — (название, город, регион). Повторная заливка того же
файла ничего не добавляет, изменённые поля обновляет. Пишет только в справочник
`School`; банк задач и профили не трогает, поэтому снимка «до» не нужно — откат =
`School.objects.all().delete()` и заливка прежнего файла.
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems import school_sync
from problems.models import School
from problems.school_search import number_in_name

REQUIRED = ('name', 'city')


class Command(BaseCommand):
    help = 'Справочник школ для подсказок онбординга из CSV (идемпотентно, --apply пишет).'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--apply', action='store_true', help='записать (без флага — сухой прогон)')
        parser.add_argument('--format', choices=('csv', 'raoo'), default='csv',
                            help='csv — свой CSV; raoo — выгрузка реестра Рособрнадзора')

    def handle(self, path, apply=False, format='csv', **options):
        if format == 'raoo':
            return self._raoo(path, apply)
        try:
            with open(path, encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
        except OSError as error:
            raise CommandError('Не открыть файл: %s' % error)
        if rows and any(column not in rows[0] for column in REQUIRED):
            raise CommandError('Нужны колонки: %s' % ', '.join(REQUIRED))

        before = School.objects.count()
        created = updated = same = skipped = 0
        with transaction.atomic():
            for row in rows:
                name = (row.get('name') or '').strip()[:300]
                city = (row.get('city') or '').strip()[:120]
                if not name or not city:
                    skipped += 1
                    continue
                raw_number = (row.get('number') or '').strip()
                number = int(raw_number) if raw_number.isdigit() else number_in_name(name)
                values = {'short_name': (row.get('short_name') or '').strip()[:200],
                          'kind': (row.get('kind') or '').strip()[:40], 'number': number}
                region = (row.get('region') or '').strip()[:200]
                school = School.objects.filter(name=name, city=city, region=region,
                                               registry_id='').first()
                if school is None:
                    created += 1
                    if apply:
                        School.objects.create(name=name, city=city, region=region, **values)
                elif any(getattr(school, k) != v for k, v in values.items()):
                    updated += 1
                    if apply:
                        for key, value in values.items():
                            setattr(school, key, value)
                        school.save()
                else:
                    same += 1
            if not apply:
                transaction.set_rollback(True)

        after = School.objects.count()
        self.stdout.write('Строк в файле: %d · новых: %d · обновлено: %d · без изменений: %d · '
                          'пропущено (нет названия или города): %d' % (len(rows), created, updated,
                                                                       same, skipped))
        self.stdout.write('Школ в справочнике: было %d, стало %d%s' % (
            before, after, '' if apply else ' (сухой прогон, ничего не записано; --apply пишет)'))

    def _raoo(self, path, apply):
        before = School.objects.filter(is_active=True).count()
        try:
            counts = school_sync.apply_rows(school_sync.read_rows(path), apply=apply)
        except school_sync.SyncError as error:
            raise CommandError('Реестр не загружен, таблица не тронута: %s' % error)
        self.stdout.write('Школ в файле: %d · новых: %d · изменено: %d · выключено: %d' % (
            counts['total'], counts['added'], counts['changed'], counts['deactivated']))
        self.stdout.write('Действующих школ в справочнике: было %d, стало %d%s' % (
            before, School.objects.filter(is_active=True).count(),
            '' if apply else ' (сухой прогон, ничего не записано; --apply пишет)'))
