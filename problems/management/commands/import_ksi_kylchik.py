"""
Management command: import_ksi_kylchik

Импортирует задачи из «Задачи КСИ кыльчик.pdf» (Сергей Кыльчик, Олмат).
PDF имеет нестандартную кодировку шрифтов, поэтому текст извлекается
через OCR с помощью Swift и macOS Vision framework.

Запуск:
    python manage.py import_ksi_kylchik
    python manage.py import_ksi_kylchik --dry-run
    python manage.py import_ksi_kylchik --ocr-file /path/to/kylchik.txt

Структура PDF:
    - 69 страниц, ~30 «Домашних заданий»
    - Задачи маркируются «Задача N» или «Задача N (...)»
    - SourceReference.note = «ДЗ N, Задача M»
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.models import Job, Problem, Source, SourceReference

PDF_PATH = (
    Path(settings.BASE_DIR)
    / 'materials' / 'attachments'
    / 'Задачи КСИ кыльчик.pdf'
)

SWIFT_SCRIPT = Path(settings.BASE_DIR) / 'ocr_pdf.swift'

BATCH_SIZE = 20

# Маркер страницы в OCR-выводе
PAGE_MARKER_RE = re.compile(r'^===PAGE_\d+===', re.MULTILINE)

# Заголовок раздела: «Домашнее задание N.» (с OCR-артефактами вроде «Донатнее»)
DZ_RE = re.compile(r'\w+нее\s+задание\s+(\d+)', re.IGNORECASE)

# Маркер задачи: «Задача N» в начале строки или после переноса
TASK_RE = re.compile(r'(?:^|\n)(Задача\s+\d+)', re.MULTILINE)

# Мусор: «tg: ...», «Сергей Кыльчик», страницы-заголовки
JUNK_RE = re.compile(
    r'tg:\s*sega[^\n]*\n?|Сергей\s+Кыльчик[^\n]*\n?|Олмат\.\s*\n?',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# OCR через Swift + Vision framework
# ---------------------------------------------------------------------------

def run_ocr(pdf_path: Path, ocr_file: Path, stderr_write) -> bool:
    """Запускает Swift-скрипт OCR, результат пишет в ocr_file."""
    if not SWIFT_SCRIPT.exists():
        stderr_write(f'Swift-скрипт не найден: {SWIFT_SCRIPT}')
        return False

    stderr_write(f'Запускаю OCR (Swift Vision)... это займёт ~2–3 минуты')

    cmd = [
        'swift', str(SWIFT_SCRIPT),
        str(pdf_path), '0', '1000',   # страницы 0-1000 (все)
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(settings.BASE_DIR),
        )
    except subprocess.TimeoutExpired:
        stderr_write('OCR завис (timeout 10 мин)')
        return False
    except FileNotFoundError:
        stderr_write('swift не найден в PATH')
        return False

    if result.returncode != 0:
        stderr_write(f'OCR завершился с ошибкой: {result.stderr[:200]}')
        return False

    ocr_file.write_text(result.stdout, encoding='utf-8')
    stderr_write(f'OCR готов, символов: {len(result.stdout)}')
    return True


# ---------------------------------------------------------------------------
# Парсинг OCR-текста
# ---------------------------------------------------------------------------

def join_hyphens(text: str) -> str:
    """Убирает переносы вида «слово-\\nпродолжение» → «словопродолжение»."""
    return re.sub(r'-\n(\S)', lambda m: m.group(1), text)


def parse_problems(ocr_text: str) -> list:
    """
    Разбивает OCR-текст на задачи.

    Возвращает список словарей:
        dz_num: int  — номер домашнего задания
        task_num: int — номер задачи в рамках ДЗ
        statement: str
    """
    # Убираем маркеры страниц (===PAGE_N===)
    text = PAGE_MARKER_RE.sub('\n', ocr_text)

    # Убираем мусорные строки (tg:, Сергей Кыльчик, Олмат.)
    text = JUNK_RE.sub('', text)

    # Убираем переносы слов
    text = join_hyphens(text)

    # Нормализуем пробелы и переносы
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    records = []
    current_dz = 0

    # Разбиваем по маркерам «Задача N»
    # Сначала ищем все вхождения «Задача N» с их позициями
    task_starts = list(TASK_RE.finditer(text))

    for idx, m in enumerate(task_starts):
        # Тело задачи — от текущей «Задача N» до следующей
        body_start = m.start(1)
        body_end = task_starts[idx + 1].start(1) if idx + 1 < len(task_starts) else len(text)
        body = text[body_start:body_end].strip()

        # Ищем номер задачи
        num_match = re.match(r'Задача\s+(\d+)', body)
        task_num = int(num_match.group(1)) if num_match else (idx + 1)

        # Ищем «Домашнее задание N» в тексте ДО этой задачи
        # (обновляем текущий ДЗ)
        preceding = text[:body_start]
        dz_matches = list(DZ_RE.finditer(preceding))
        if dz_matches:
            current_dz = int(dz_matches[-1].group(1))

        # Убираем мусор из тела задачи
        body = JUNK_RE.sub('', body).strip()
        # Убираем строку «Домашнее задание N.» если попала в тело
        body = re.sub(r'Дом[а-яё\w]*е\s+задание\s+\d+\.?\s*\n?', '', body).strip()

        if len(body) < 20:
            continue

        records.append({
            'dz_num': current_dz,
            'task_num': task_num,
            'statement': body,
        })

    return records


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Импортирует задачи из «Задачи КСИ кыльчик.pdf» через OCR'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default=str(PDF_PATH),
            help='Путь к PDF',
        )
        parser.add_argument(
            '--ocr-file', type=str, default='',
            help='Путь к уже готовому OCR-файлу (чтобы пропустить OCR)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Показать статистику без записи в базу',
        )

    def handle(self, *args, **options):
        pdf_path = Path(options['file'])
        dry_run = options['dry_run']
        ocr_file_arg = options['ocr_file']

        if not pdf_path.exists():
            self.stderr.write(self.style.ERROR(f'Файл не найден: {pdf_path}'))
            return

        # ── OCR ──────────────────────────────────────────────────────────
        if ocr_file_arg:
            ocr_path = Path(ocr_file_arg)
            if not ocr_path.exists():
                self.stderr.write(self.style.ERROR(f'OCR-файл не найден: {ocr_path}'))
                return
            self.stdout.write(f'Читаю готовый OCR-файл: {ocr_path}')
            ocr_text = ocr_path.read_text(encoding='utf-8')
        else:
            ocr_path = Path(tempfile.gettempdir()) / 'kylchik_ocr_import.txt'
            if ocr_path.exists() and ocr_path.stat().st_size > 10000:
                self.stdout.write(f'Использую кэш OCR: {ocr_path}')
                ocr_text = ocr_path.read_text(encoding='utf-8')
            else:
                ok = run_ocr(pdf_path, ocr_path, self.stderr.write)
                if not ok:
                    return
                ocr_text = ocr_path.read_text(encoding='utf-8')

        self.stdout.write(f'OCR-текст: {len(ocr_text)} символов')

        # ── Парсинг ───────────────────────────────────────────────────────
        records = parse_problems(ocr_text)
        total = len(records)
        self.stdout.write(f'Задач распознано: {total}')

        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')
            for r in records[:5]:
                self.stdout.write(
                    f'\n--- ДЗ {r["dz_num"]}, Задача {r["task_num"]} ---\n'
                    f'{r["statement"][:180]}'
                )
            return

        # ── Источник ─────────────────────────────────────────────────────
        source, created_src = Source.objects.get_or_create(
            name='КСИ — Задачи Кыльчик',
            defaults={
                'kind': 'сборник задач',
                'note': (
                    'Сергей Кыльчик (КСИ), Олмат. '
                    '~30 домашних заданий по олимпиадной экономике.'
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
                    stmt_hash = hashlib.md5(stmt.encode()).hexdigest()

                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue

                    try:
                        with transaction.atomic():
                            # Заголовок — первые ~80 символов первой строки
                            first_line = stmt.split('\n')[0].strip()
                            title = first_line[:80] if first_line else (
                                f'ДЗ {rec["dz_num"]}, Задача {rec["task_num"]}'
                            )

                            p = Problem.objects.create(
                                title=title,
                                statement=stmt,
                                solution='',
                                status=Problem.Status.DRAFT,
                                content_hash=stmt_hash,
                                problem_type='',
                            )

                            SourceReference.objects.create(
                                problem=p,
                                source=source,
                                note=f'ДЗ {rec["dz_num"]}, Задача {rec["task_num"]}',
                            )

                        existing_hashes.add(stmt_hash)
                        created += 1

                    except Exception as exc:
                        errors += 1
                        self.stderr.write(
                            f'  Ошибка ДЗ {rec["dz_num"]} Задача {rec["task_num"]}: {exc}'
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
