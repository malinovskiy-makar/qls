"""
Management command: import_ksigma

Импортирует «решалки» КСИГМА (@ksigma_education) из внешних PDF внутри
архива: materials/Archive 6/Archive 5/Archive 3/Archive.zip

Файлы серий «Решалка», «HW», «ПЗЭ», «Пробник». Каждый PDF = условие задачи
+ полное решение в одном документе.

Имена файлов в ZIP — UTF-8, но без флага → декодируются
`name.encode('cp437').decode('utf-8')`. Resource-fork двойники `._*` пропускаются.

Два типа файлов:
  - Нативные (текстовый слой читается, доля кириллицы > 0.35) — парсятся напрямую.
  - Битый LaTeX-cmap / сканы (кириллицы ~0) — через OCR macOS Vision
    (ocr_pdf.swift, как в import_ksi_kylchik). Результат OCR кэшируется.

Разбор: текст режется по «Задача N», внутри условие/решение делятся по «Решение»
(или «Ответ»). Подпункты «(a)/(б)…» → ProblemPart, баллы «(N балл…)» → points.

status=draft, difficulty=5. Источник «КСИГМА — Решалки».
Дедупликация по content_hash (md5 условия).

Запуск:
    python manage.py import_ksigma
    python manage.py import_ksigma --dry-run
    python manage.py import_ksigma --no-ocr   (только нативные файлы)
"""
import hashlib
import io
import re
import subprocess
import zipfile
from pathlib import Path

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from problems.models import Job, Problem, ProblemPart, Source, SourceReference


ZIP_PATH = (Path(settings.BASE_DIR) / 'materials' / 'Archive 6' / 'Archive 5'
            / 'Archive 3' / 'Archive.zip')
SWIFT_SCRIPT = Path(settings.BASE_DIR) / 'ocr_pdf.swift'
OCR_CACHE_DIR = Path(settings.BASE_DIR) / 'materials' / 'attachments' / 'ksigma_ocr_cache'
SOURCE_NAME = 'КСИГМА — Решалки'
DIFFICULTY = 5

KEEP_RE = re.compile(r'Решалка|HW|ПЗЭ|Пробник', re.IGNORECASE)
TASK_RE = re.compile(r'(?:^|\n)\s*Задача\s+(\d+)')
SOL_RE = re.compile(r'(?m)^\s*(?:Решение|Ответ)\s*:?')
SUB_RE = re.compile(r'(?m)^\s*\(([а-яёa-zА-ЯЁ])\)\s')
POINTS_RE = re.compile(r'\((\d+)\s*балл[а-я]*\)')
PAGE_OCR_RE = re.compile(r'(?m)^===PAGE_\d+===\s*$')
JUNK_RE = re.compile(
    r'(?mi)^.*(?:tg:\s*ksigma|@?ksigma_education|КСИГМА\.?\s*$).*$'
)


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def decode_name(name: str) -> str:
    try:
        return name.encode('cp437').decode('utf-8')
    except Exception:
        return name


def cyr_ratio(text: str) -> float:
    if not text:
        return 0.0
    c = sum(1 for ch in text if 'а' <= ch.lower() <= 'я')
    return c / max(1, len(text))


def join_hyphens(text: str) -> str:
    return re.sub(r'(\w)-\n(\S)', r'\1\2', text)


def clean(text: str) -> str:
    text = PAGE_OCR_RE.sub('\n', text)
    text = JUNK_RE.sub('', text)
    text = join_hyphens(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def parse_tasks(text: str):
    """Возвращает список (num, statement, solution, [(label, sub_text, points)])."""
    text = clean(text)
    starts = list(TASK_RE.finditer(text))
    out = []
    for i, m in enumerate(starts):
        num = int(m.group(1))
        s = m.start()
        e = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        block = text[s:e].strip()
        # убираем «Задача N.» из начала
        block = re.sub(r'^\s*Задача\s+\d+\.?\s*', '', block).strip()
        sm = SOL_RE.search(block)
        if sm:
            condition = block[:sm.start()].strip()
            solution = block[sm.end():].strip()
        else:
            condition = block
            solution = ''
        if len(condition) < 15:
            continue
        # подпункты условия
        parts = []
        subs = list(SUB_RE.finditer(condition))
        for j, sub in enumerate(subs):
            se = subs[j + 1].start() if j + 1 < len(subs) else len(condition)
            sub_text = condition[sub.end():se].strip()
            pm = POINTS_RE.search(sub_text)
            pts = int(pm.group(1)) if pm else None
            parts.append((sub.group(1), sub_text, pts))
        out.append((num, condition, solution, parts))
    return out


def run_ocr(pdf_bytes: bytes, base: str, stderr_write, timeout=480) -> str:
    """OCR файла через swift+Vision. Кэширует результат."""
    OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = OCR_CACHE_DIR / (base + '.txt')
    if cache.exists() and cache.stat().st_size > 300:
        return cache.read_text(encoding='utf-8')
    if not SWIFT_SCRIPT.exists():
        stderr_write(f'  Нет swift-скрипта: {SWIFT_SCRIPT}')
        return ''
    tmp = Path('/tmp/ksigma_ocr_tmp.pdf')   # без пробелов — нужно для file:// URL
    tmp.write_bytes(pdf_bytes)
    try:
        res = subprocess.run(
            ['swift', str(SWIFT_SCRIPT), str(tmp), '0', '1000'],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(settings.BASE_DIR))
    except subprocess.TimeoutExpired:
        stderr_write(f'  OCR timeout ({base})')
        return ''
    except FileNotFoundError:
        stderr_write('  swift не найден в PATH')
        return ''
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    if res.returncode != 0:
        stderr_write(f'  OCR ошибка ({base}): {res.stderr[:120]}')
        return ''
    cache.write_text(res.stdout, encoding='utf-8')
    return res.stdout


class Command(BaseCommand):
    help = 'Импортирует решалки КСИГМА из Archive.zip (нативно + OCR)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--no-ocr', action='store_true',
                            help='Только нативные файлы, без OCR')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        no_ocr = options['no_ocr']

        if not ZIP_PATH.exists():
            self.stderr.write(self.style.ERROR(f'Нет архива: {ZIP_PATH}'))
            return

        z = zipfile.ZipFile(str(ZIP_PATH))
        # отобрать подходящие PDF
        targets = []  # (zipinfo, base)
        for zi in z.infolist():
            name = decode_name(zi.filename)
            base = name.split('/')[-1]
            if base.startswith('._') or not base.lower().endswith('.pdf'):
                continue
            if 'Подборки' in name:   # вложенный ОЭШ 2022 — не наш
                continue
            if not KEEP_RE.search(base):
                continue
            targets.append((zi, base))

        self.stdout.write(f'Подходящих PDF: {len(targets)}')
        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run.'))

        existing_hashes = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        source = job = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={'kind': 'сборник задач',
                          'note': 'КСИГМА (@ksigma_education) — решалки, олимпиадный уровень'})
            job = Job.objects.create(kind='import', status='running',
                                     params={'source': SOURCE_NAME, 'files': len(targets)})

        created = skipped = errors = ocr_used = 0
        files_native = files_ocr = files_skipped = 0

        # ── две очереди: сначала нативные (быстро), потом OCR ─────────────
        native_q, ocr_q = [], []
        for zi, base in targets:
            try:
                data = z.read(zi)
                doc = fitz.open(stream=data, filetype='pdf')
                text = '\n'.join(doc[i].get_text() for i in range(len(doc)))
                doc.close()
            except Exception as exc:
                self.stderr.write(f'  Ошибка чтения {base}: {exc}')
                errors += 1
                continue
            if cyr_ratio(text) > 0.35 and TASK_RE.search(text):
                native_q.append((base, text))
            else:
                ocr_q.append((zi, base))

        def import_file(base, text, via):
            nonlocal created, skipped, errors
            tasks = parse_tasks(text)
            if not tasks:
                return 0
            n_local = 0
            for num, condition, solution, parts in tasks:
                try:
                    h = md5(condition)
                    if h in existing_hashes:
                        skipped += 1
                        continue
                    if dry_run:
                        created += 1
                        n_local += 1
                        existing_hashes.add(h)
                        continue
                    with transaction.atomic():
                        title = condition.split('\n')[0].strip()[:80] or f'{base}, Задача {num}'
                        problem = Problem.objects.create(
                            title=title, statement=condition, solution=solution,
                            status=Problem.Status.DRAFT, difficulty=DIFFICULTY,
                            content_hash=h)
                        SourceReference.objects.create(
                            problem=problem, source=source,
                            note=f'{base}, Задача {num} [{via}]')
                        for order, (label, sub_text, pts) in enumerate(parts):
                            ProblemPart.objects.create(
                                problem=problem, label=label, statement=sub_text,
                                answer='', points=pts, order=order)
                    created += 1
                    n_local += 1
                    existing_hashes.add(h)
                except Exception as exc:
                    self.stderr.write(f'  Ошибка {base} Задача {num}: {exc}')
                    errors += 1
            return n_local

        # пасс 1 — нативные
        for base, text in native_q:
            n = import_file(base, text, 'native')
            files_native += 1
            self.stdout.write(f'  [native] {base[:46]:46} +{n}')

        # пасс 2 — OCR
        if no_ocr:
            self.stdout.write(f'OCR пропущен (--no-ocr). Файлов на OCR было: {len(ocr_q)}')
        else:
            for zi, base in ocr_q:
                try:
                    data = z.read(zi)
                except Exception as exc:
                    self.stderr.write(f'  Ошибка чтения {base}: {exc}')
                    errors += 1
                    continue
                self.stdout.write(f'  [OCR…] {base}')
                ocr_text = run_ocr(data, base, self.stderr.write)
                if not ocr_text or cyr_ratio(ocr_text) < 0.3 or not TASK_RE.search(ocr_text):
                    files_skipped += 1
                    self.stdout.write(f'  [skip ] {base[:46]:46} (OCR без задач)')
                    continue
                ocr_used += 1
                n = import_file(base, ocr_text, 'ocr')
                files_ocr += 1
                self.stdout.write(f'  [ocr  ] {base[:46]:46} +{n}')
                if not dry_run and job:
                    job.progress = min(99, int((files_native + files_ocr) /
                                               max(1, len(targets)) * 100))
                    job.save(update_fields=['progress'])

        if not dry_run and job:
            job.status = 'done' if errors == 0 else 'failed'
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = {'created': created, 'skipped': skipped, 'errors': errors,
                          'native_files': files_native, 'ocr_files': files_ocr}
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nИтог КСИГМА: создано {created}, пропущено {skipped}, ошибок {errors}\n'
            f'  Файлов: нативных {files_native}, через OCR {files_ocr}, '
            f'пропущено {files_skipped}'))
