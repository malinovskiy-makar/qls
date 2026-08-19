"""
Management command: import_pdf_shpits

Импортирует задачи из «Сложные олимпиадные задачки» Фрица фон Шпицрутена.
В PDF каждая задача содержит условие и решение вместе.
Использует PyMuPDF для извлечения текста (pdftotext недоступен).

Запуск:
    python manage.py import_pdf_shpits
    python manage.py import_pdf_shpits --file /path/to/file.pdf
    python manage.py import_pdf_shpits --dry-run
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
    / 'materials' / 'attachments'
    / 'задачник шпицруттена (сложные олимпиадные задачки).pdf'
)

BATCH_SIZE = 20

# Шапка страницы (одна строка с автором и диапазоном задач)
HEADER_RE = re.compile(r'^Фриц фон Шпицрутен.*\n', re.MULTILINE)

# Маркер задачи: S001. S002. … S060.
TASK_MARKER_RE = re.compile(r'S(\d{3})\.')

# «Решение» как отдельная строка (с возможными пробелами вокруг)
SOLUTION_SEP_RE = re.compile(r'\n[ \t]*Решение[ \t]*\n', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Парсинг
# ---------------------------------------------------------------------------

def extract_full_text(pdf_path: Path) -> str:
    """Извлекает текст PDF, убирает шапки страниц."""
    doc = fitz.open(str(pdf_path))
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    full = '\n'.join(pages)
    full = HEADER_RE.sub('', full)
    return full


def parse_tasks(text: str) -> list:
    """
    Разбивает текст на задачи по маркерам S001., S002., …
    Для каждой задачи разделяет условие и решение по строке «Решение».

    Возвращает list[dict]:
        num_str, statement, solution
    """
    # Разбиваем: [...prefix, S001, text1, S002, text2, ...]
    parts = TASK_MARKER_RE.split(text)
    # parts[0] — текст до S001 (обычно пустой/шапка)
    # parts[1] = "001", parts[2] = текст S001
    # parts[3] = "002", parts[4] = текст S002  …

    records = []
    i = 1
    while i + 1 < len(parts):
        num_str = parts[i]       # "001", "002", …
        body = parts[i + 1]      # текст задачи до следующего маркера

        # Убираем ведущую точку и пробелы (маркер был "S001.", остаток — ". ")
        body = body.lstrip('. \t')

        # Разделяем на условие и решение
        sep = SOLUTION_SEP_RE.search(body)
        if sep:
            statement = body[:sep.start()].strip()
            solution = body[sep.end():].strip()
        else:
            statement = body.strip()
            solution = ''

        if statement:
            records.append({
                'num_str': num_str,
                'statement': statement,
                'solution': solution,
            })

        i += 2

    return records


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Импортирует задачи из PDF Шпицрутена (Сложные олимпиадные задачки)'

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

        # ── Извлечение и парсинг ─────────────────────────────────────────
        self.stdout.write(f'Читаю PDF: {pdf_path.name}')
        full_text = extract_full_text(pdf_path)
        self.stdout.write(f'Текст извлечён, символов: {len(full_text)}')

        records = parse_tasks(full_text)
        total = len(records)
        self.stdout.write(f'Задач распознано: {total}')

        has_solution = sum(1 for r in records if r['solution'])
        self.stdout.write(f'Из них с решением: {has_solution}')

        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')
            for r in records[:3]:
                self.stdout.write(
                    f'\n--- S{r["num_str"]} ---\n'
                    f'Условие: {r["statement"][:120]}\n'
                    f'Решение: {r["solution"][:80]}'
                )
            return

        # ── Источник ─────────────────────────────────────────────────────
        source, created_src = Source.objects.get_or_create(
            name='Шпицруттен — Сложные олимпиадные задачи',
            defaults={
                'kind': 'сборник задач',
                'note': (
                    'Фриц фон Шпицрутен, «Сложные олимпиадные задачки», '
                    'задачи S001–S060 с решениями.'
                ),
            },
        )
        self.stdout.write(
            f'Источник «{source.name}» '
            f'{"создан" if created_src else "найден"}: #{source.pk}'
        )

        # ── Job ───────────────────────────────────────────────────────────
        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'file': str(pdf_path), 'total': total},
        )
        self.stdout.write(f'Job #{job.pk} создан')

        # ── Кэш хэшей ────────────────────────────────────────────────────
        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='')
            .values_list('content_hash', flat=True)
        )

        # ── Основной цикл ─────────────────────────────────────────────────
        created = skipped = errors = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = records[batch_start:batch_start + BATCH_SIZE]

            with transaction.atomic():
                for rec in batch:
                    stmt = rec['statement']
                    stmt_hash = hashlib.md5(stmt.encode(), usedforsecurity=False).hexdigest()

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
                                solution=rec['solution'],
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

        # ── Завершаем Job ─────────────────────────────────────────────────
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
