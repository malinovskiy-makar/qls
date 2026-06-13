"""
Management command: import_shpits_part2

Импортирует задачи из «Часть 2» Георгия Пермякова (Фриц фон Шпицрутен).
Файл: materials/Archive 6/…/Шпицрутен. Часть 2.pdf
20 задач (1)–(20), нумеруются как S061–S080. Решений нет.

Запуск:
    python manage.py import_shpits_part2
    python manage.py import_shpits_part2 --dry-run
"""
import hashlib
import re
from pathlib import Path

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.models import Job, Problem, Source, SourceReference


PDF_PATH = (
    Path(settings.BASE_DIR)
    / 'materials' / 'Archive 6' / 'Archive 5' / 'Archive 3'
    / 'drive-download-20260513T172045Z-3-001 copy'
    / 'Шпицрутен. Часть 2.pdf'
)

BATCH_SIZE = 20

# Шапка
HEADER_RE = re.compile(
    r'^\d+\s*\n.*?Шпицрутен.*?\n', re.MULTILINE
)

# Маркер задачи: (1) (2) ... (20) — в начале строки
TASK_MARKER_RE = re.compile(r'\n\(\d+\)\s')

# Смещение: задача (1) в этом файле = S061
S_OFFSET = 60


def extract_full_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return '\n'.join(pages)


def parse_tasks(text: str) -> list:
    """
    Разбивает текст на задачи по маркерам вида (N).
    Нумерует последовательно: 1-я задача → S061, 2-я → S062, …
    """
    # Находим позиции всех маркеров
    positions = [(m.start(), m.end()) for m in TASK_MARKER_RE.finditer(text)]

    records = []
    for idx, (start, end) in enumerate(positions):
        s_num = idx + 1 + S_OFFSET  # S061, S062, …
        # Тело задачи — до следующего маркера или конца текста
        body_start = end
        body_end = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        body = text[body_start:body_end].strip()

        if body:
            records.append({
                'num_str': f'{s_num:03d}',
                'statement': body,
            })

    return records


class Command(BaseCommand):
    help = 'Импортирует задачи S061–S080 из PDF Шпицрутена Часть 2'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default=str(PDF_PATH),
            help='Путь к PDF файлу',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Показать статистику без записи в базу',
        )

    def handle(self, *args, **options):
        pdf_path = Path(options['file'])
        dry_run = options['dry_run']

        if not pdf_path.exists():
            self.stderr.write(self.style.ERROR(f'Файл не найден: {pdf_path}'))
            return

        self.stdout.write(f'Читаю PDF: {pdf_path.name}')
        full_text = extract_full_text(pdf_path)
        self.stdout.write(f'Текст извлечён, символов: {len(full_text)}')

        records = parse_tasks(full_text)
        total = len(records)
        self.stdout.write(f'Задач распознано: {total}')

        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')
            for r in records[:3]:
                self.stdout.write(
                    f'\n--- S{r["num_str"]} ---\n'
                    f'Условие: {r["statement"][:150]}'
                )
            return

        # Источник — тот же, что Part 1
        source, created_src = Source.objects.get_or_create(
            name='Шпицруттен — Сложные олимпиадные задачи',
            defaults={
                'kind': 'сборник задач',
                'note': 'Фриц фон Шпицрутен, сложные олимпиадные задачи.',
            },
        )
        self.stdout.write(
            f'Источник «{source.name}» '
            f'{"создан" if created_src else "найден"}: #{source.pk}'
        )

        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'file': str(pdf_path), 'total': total},
        )
        self.stdout.write(f'Job #{job.pk} создан')

        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='')
            .values_list('content_hash', flat=True)
        )

        created = skipped = errors = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = records[batch_start:batch_start + BATCH_SIZE]

            with transaction.atomic():
                for rec in batch:
                    stmt = rec['statement']
                    stmt_hash = hashlib.md5(stmt.encode()).hexdigest()

                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue

                    try:
                        with transaction.atomic():
                            title = stmt.split('\n')[0].strip()[:80]
                            if not title:
                                title = f'Задача S{rec["num_str"]}'

                            p = Problem.objects.create(
                                title=title,
                                statement=stmt,
                                solution='',
                                difficulty=5,
                                difficulty_native='сложная',
                                status=Problem.Status.DRAFT,
                                content_hash=stmt_hash,
                                problem_type='',
                            )

                            SourceReference.objects.create(
                                problem=p,
                                source=source,
                                note=f'S{rec["num_str"]}',
                            )

                        existing_hashes.add(stmt_hash)
                        created += 1

                    except Exception as exc:
                        errors += 1
                        self.stderr.write(
                            f'  Ошибка S{rec["num_str"]}: {exc}'
                        )

            done = min(batch_start + BATCH_SIZE, total)
            progress = int(done / total * 100) if total else 100
            job.progress = progress
            job.result = {'created': created, 'skipped': skipped, 'errors': errors}
            job.save(update_fields=['progress', 'result'])
            self.stdout.write(
                f'  [{done:3d}/{total}]  '
                f'создано: {created},  пропущено: {skipped},  ошибок: {errors}'
            )

        job.status = Job.Status.DONE
        job.progress = 100
        job.finished_at = timezone.now()
        job.result = {'created': created, 'skipped': skipped, 'errors': errors}
        job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!\n'
            f'  Создано задач:     {created}\n'
            f'  Пропущено (дубли): {skipped}\n'
            f'  Ошибок:            {errors}\n'
            f'  Job #{job.pk}: {job.status}'
        ))
