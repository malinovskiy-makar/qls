"""
Management command: import_ile_raw

Импортирует задачи из problems.json (сырой датасет ILE) — добавляет только те,
которых ещё нет в базе (дедупликация по URL через SourceReference).

Запуск:
    python manage.py import_ile_raw
    python manage.py import_ile_raw --file /path/to/problems.json
    python manage.py import_ile_raw --dry-run   # только считает, не пишет
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from problems.models import Job, Problem, Source, SourceReference, Tag


DEFAULT_FILE = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'Archive 6'
    / 'ile_dataset 2 copy'
    / 'problems.json'
)

BATCH_SIZE = 100


def clean_statement(text: str, title: str) -> str:
    """Убирает навигацию сайта ILE из начала и конца текста задачи."""
    if not text:
        return ''

    for footer in ('Войдите или зарегистрируйтесь',
                   'войдите или зарегистрируйтесь',
                   'О проекте Сайт создан'):
        idx = text.find(footer)
        if idx > 0:
            text = text[:idx]

    marker = 'Версия для печати'
    idx = text.find(marker)
    if idx != -1:
        after = text[idx + len(marker):]
        for skip in ('Только условие',
                     'Условие с решением и ответом',
                     'Только решение и ответ'):
            after = after.replace(skip, '', 1)
        return after.strip()

    if title:
        p1 = text.find(title)
        if p1 != -1:
            p2 = text.find(title, p1 + 1)
            if p2 != -1:
                return text[p2 + len(title):].strip()

    return text[200:].strip() if len(text) > 200 else text.strip()


class Command(BaseCommand):
    help = 'Импортирует новые задачи из ILE сырого датасета (problems.json)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default=str(DEFAULT_FILE),
            help='Путь к problems.json',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать статистику, ничего не записывать в базу',
        )

    def handle(self, *args, **options):
        filepath = Path(options['file'])
        dry_run = options['dry_run']

        if not filepath.exists():
            self.stderr.write(self.style.ERROR(f'Файл не найден: {filepath}'))
            return

        self.stdout.write(f'Загружаю: {filepath}')
        with open(filepath, encoding='utf-8') as f:
            records = json.load(f)
        total = len(records)
        self.stdout.write(f'Записей в файле: {total}')

        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')

        ile_source, created_source = Source.objects.get_or_create(
            name='ILE / iloveeconomics.ru',
            defaults={
                'kind': 'онлайн-банк задач',
                'note': (
                    'Задачи с сайта iloveeconomics.ru — онлайн-банк '
                    'олимпиадных задач по экономике ЛЭШ (ВШЭ).'
                ),
            },
        )
        action = 'создан' if created_source else 'найден'
        self.stdout.write(f'Источник ILE {action}: #{ile_source.pk}')

        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'file': str(filepath), 'total': total, 'dry_run': dry_run},
        )
        self.stdout.write(f'Job #{job.pk} создан, статус: {job.status}')

        existing_urls: set = set(
            SourceReference.objects.filter(source=ile_source)
            .values_list('url', flat=True)
        )
        self.stdout.write(
            f'Уже в базе: {len(existing_urls)} задач из этого источника'
        )

        created = skipped = errors = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = records[batch_start:batch_start + BATCH_SIZE]

            with transaction.atomic():
                for record in batch:
                    url = (record.get('url') or '').strip()

                    if url and url in existing_urls:
                        skipped += 1
                        continue

                    try:
                        with transaction.atomic():
                            title = (record.get('title') or '').strip()[:299]
                            raw_text = record.get('text') or ''
                            statement = clean_statement(raw_text, title)
                            if not statement:
                                statement = title or '—'

                            if not dry_run:
                                problem = Problem.objects.create(
                                    title=title,
                                    statement=statement,
                                    status=Problem.Status.PUBLISHED,
                                    problem_type='',
                                )

                                SourceReference.objects.create(
                                    problem=problem,
                                    source=ile_source,
                                    url=url[:199] if url else '',
                                )
                                if url:
                                    existing_urls.add(url)

                        created += 1

                    except Exception as exc:
                        errors += 1
                        self.stderr.write(
                            f'  Ошибка в записи '
                            f'«{record.get("title", "?")}»: {exc}'
                        )

            done = min(batch_start + BATCH_SIZE, total)
            progress = int(done / total * 100)

            if not dry_run:
                job.progress = progress
                job.result = {
                    'created': created,
                    'skipped': skipped,
                    'errors': errors,
                }
                job.save(update_fields=['progress', 'result'])

            self.stdout.write(
                f'  [{done:4d}/{total}]  '
                f'создано: {created},  '
                f'пропущено: {skipped},  '
                f'ошибок: {errors}'
            )

        if not dry_run:
            job.status = Job.Status.DONE
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = {
                'created': created,
                'skipped': skipped,
                'errors': errors,
            }
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!\n'
            f'  Создано задач:         {created}\n'
            f'  Пропущено (дубли):     {skipped}\n'
            f'  Ошибок:                {errors}\n'
            f'  Job #{job.pk}: {job.status}'
        ))
