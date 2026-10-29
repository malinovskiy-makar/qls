# -*- coding: utf-8 -*-
"""Синхронизация справочника школ с реестром Рособрнадзора (раунд 3, 29.10.2026).

    manage.py sync_schools               # проверить свежесть, скачать, обновить таблицу
    manage.py sync_schools --dry-run     # то же, но только посчитать, ничего не писать
    manage.py sync_schools --force       # качать, даже если файл не изменился
    manage.py sync_schools --file F.zip  # не качать, взять готовый файл (.zip или .xml)

На бою — раз в неделю таймером `deploy/systemd/weconomics-schools.timer` (включение —
`docs/SERVER.md`, «Справочник школ»). Решение владельца 29.10.2026: подсказки работают по
своей таблице, свежесть даёт эта синхронизация, к Рособрнадзору на каждую букву не ходим.

Шаги:
1. Заголовки постоянной ссылки на архив (`school_registry.ARCHIVE_URL`): имя вида
   `data-YYYYMMDD-structure-20160713.zip` и размер. Совпали с последней удачной
   синхронизацией — файл тот же, не качаем (запись «файл не изменился»).
2. Скачать во временную папку: таймаут, три попытки, проверка размера и что это ZIP/XML.
3. Разобрать (`problems/school_registry.py`) и применить (`problems/school_sync.py`):
   новые добавить, изменённые поправить, исчезнувшие выключить — одной транзакцией.
4. Запись в журнал `SchoolSyncRun`: сколько добавлено, изменено, выключено.

⚠️ ПРИ ЛЮБОМ СБОЕ ТАБЛИЦА НЕ ТРОГАЕТСЯ: запись «сбой» в журнале и ненулевой код выхода
(таймер это видит). Временный файл удаляется в любом случае.
"""
import os
import shutil

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from problems import school_registry, school_sync
from problems.models_schools import SchoolSyncRun


class Command(BaseCommand):
    help = 'Справочник школ ← свежий реестр Рособрнадзора (новые, изменённые, выключенные).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='только посчитать')
        parser.add_argument('--force', action='store_true', help='качать, даже если файл тот же')
        parser.add_argument('--file', default='', help='готовый файл реестра вместо скачивания')
        parser.add_argument('--url', default=school_registry.ARCHIVE_URL,
                            help='адрес архива (по умолчанию — постоянная ссылка Рособрнадзора)')

    def handle(self, dry_run=False, force=False, file='', url='', **options):
        run = SchoolSyncRun(status=SchoolSyncRun.Status.FAILED)
        folder = None
        try:
            if file:
                if not os.path.exists(file):
                    raise school_sync.SyncError('нет файла %s' % file)
                path, run.source = file, os.path.basename(file)
                run.content_length = os.path.getsize(file)
            else:
                run.source, run.content_length = school_sync.remote_info(url)
                self.stdout.write('Свежий реестр: %s, %s байт' % (run.source or 'имя неизвестно',
                                                                   run.content_length or '?'))
                last = (SchoolSyncRun.objects.filter(status=SchoolSyncRun.Status.OK)
                        .order_by('-started_at').first())
                if (not force and last is not None and run.source
                        and (last.source, last.content_length) == (run.source, run.content_length)):
                    run.status = SchoolSyncRun.Status.SAME
                    run.message = 'тот же файл, что при синхронизации %s' % last.started_at
                    self.stdout.write('Файл не изменился с прошлого раза — не качаю.')
                    return
                folder = school_sync.temp_folder()
                path = school_sync.download(url, folder, run.content_length)
            rows = school_sync.read_rows(path)
            if not rows:
                raise school_sync.SyncError('в файле не нашлось ни одной школы')
            counts = school_sync.apply_rows(rows, apply=not dry_run)
            for name, value in counts.items():
                setattr(run, name, value)
            run.status = SchoolSyncRun.Status.DRY if dry_run else SchoolSyncRun.Status.OK
            self.stdout.write('%s: школ в файле %d, добавлено %d, изменено %d, выключено %d' % (
                'Сухой прогон' if dry_run else 'Готово', counts['total'], counts['added'],
                counts['changed'], counts['deactivated']))
        except school_sync.SyncError as error:
            run.status, run.message = SchoolSyncRun.Status.FAILED, str(error)
            raise CommandError('Синхронизация школ не удалась, таблица не тронута: %s' % error)
        finally:
            run.finished_at = timezone.now()
            run.save()
            if folder:
                shutil.rmtree(folder, ignore_errors=True)
