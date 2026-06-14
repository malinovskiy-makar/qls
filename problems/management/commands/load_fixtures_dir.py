"""
Команда load_fixtures_dir — загружает все JSON-фикстуры из папки по порядку имён.

Предназначена для ЗАПУСКА НА СЕРВЕРЕ (Render Shell), где соединение с PostgreSQL
внутреннее — быстрое и стабильное (внешний URL Render обрывает длинные транзакции).

Каждый файл грузится ОТДЕЛЬНЫМ вызовом loaddata (своя транзакция) — память
освобождается между файлами (безопасно для 512 МБ free-tier), а повтор уже
загруженного файла идемпотентен (loaddata делает INSERT-или-UPDATE по PK).

Порядок файлов задаётся именами: 10_reference → 20_problem_* → 30_sourceref_*
→ 31_part_* → 40_misc → 50_dupcand_* → 51_autotopic_* → 90_similar_* (последними,
когда все Problem уже в базе — иначе FK через границы транзакций ломается).

Запуск (в Render Shell):
    python manage.py load_fixtures_dir
    python manage.py load_fixtures_dir --dir deploy_fixtures
"""

import glob
import os
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Загружает все JSON-фикстуры из папки по порядку (для Render Shell)'

    def add_arguments(self, parser):
        parser.add_argument('--dir', type=str, default='deploy_fixtures',
                            help='Папка с фикстурами (по умолчанию deploy_fixtures)')
        parser.add_argument('--retry', type=int, default=3,
                            help='Сколько раз повторить файл при ошибке')

    def handle(self, *args, **options):
        directory = options['dir']
        max_retry = options['retry']

        # Ловим и .json, и .json.gz (loaddata читает gzip напрямую по расширению)
        files = sorted(glob.glob(os.path.join(directory, '*.json'))
                       + glob.glob(os.path.join(directory, '*.json.gz')))
        if not files:
            self.stderr.write(f'Нет файлов в {directory}/*.json[.gz]')
            return

        self.stdout.write(f'Найдено файлов: {len(files)}')
        ok = 0
        failed = []

        for i, path in enumerate(files, 1):
            name = os.path.basename(path)
            for attempt in range(1, max_retry + 1):
                self.stdout.write(f'[{i}/{len(files)}] {name} (попытка {attempt})...')
                try:
                    call_command('loaddata', path, verbosity=0)
                    ok += 1
                    break
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f'    ошибка: {exc}')
                    if attempt < max_retry:
                        time.sleep(5)
                    else:
                        failed.append(name)

        self.stdout.write('=' * 40)
        self.stdout.write(self.style.SUCCESS(f'Загружено файлов OK: {ok}'))
        if failed:
            self.stderr.write(f'Провалено: {len(failed)} — {", ".join(failed)}')
        else:
            self.stdout.write(self.style.SUCCESS('Все файлы загружены без ошибок.'))
