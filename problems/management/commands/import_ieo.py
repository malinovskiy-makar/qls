"""
Management command: import_ieo

Импортирует задания IEO (International Economics Olympiad).
Папка: materials/задания с прошлых IEO/ — 19 PDF с хэш-именами.

Два формата:
- Формат A (MCQ): в первых 3 страницах есть «MCQ 1.»
  Создаёт ProblemPart для каждого варианта A/B/C/D.
- Формат B (Open Questions): остальные файлы.
  Ищет «Open Question N.» / «Question N.» / «Problem N.»
  Создаёт ProblemPart для подпунктов (a)(b)(c) с баллами.

Запуск:
    python manage.py import_ieo
    python manage.py import_ieo --dry-run
"""
import hashlib
import re
from pathlib import Path

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from problems.models import (
    Job, Problem, ProblemPart, Source, SourceReference, Tag,
)


IEO_FOLDER = Path(settings.BASE_DIR) / 'materials' / 'задания с прошлых IEO'
BATCH_SIZE = 20
DIFFICULTY = 4
SOURCE_NAME = 'IEO — International Economics Olympiad'

# ──────────────────────────────────────────────────────────────────────────────
# Регулярные выражения
# ──────────────────────────────────────────────────────────────────────────────

YEAR_RE = re.compile(r'\b(20\d{2})\b')
TRACK_RE = re.compile(
    r'\b(Macroeconomics|Microeconomics|Financial\s+Literacy|Finance|Economics)\b',
    re.IGNORECASE,
)
# Невидимые символы Unicode (нулевые пробелы и т. п.)
INVISIBLE_RE = re.compile(r'[​‌‍﻿]+')

# Формат A — MCQ-блоки
MCQ_DETECT_RE = re.compile(r'MCQ\s+1\.')
MCQ_BLOCK_RE = re.compile(
    r'MCQ\s+(\d+)\.\s+([^\n]+)\n(.*?)(?=MCQ\s+\d+\.|\Z)',
    re.DOTALL,
)

# Правильный ответ в SF1 («Correct answer: B»)
MCQ_CORRECT_ANS_RE = re.compile(r'Correct\s*answer\s*:\s*([A-D])\.?', re.IGNORECASE)

# Объяснение (после «Explanation: ...»)
EXPLANATION_RE = re.compile(
    r'Explanation\s*[:\.\s]+\n?(.*?)(?=\nMCQ\s|\nIEO\s|\nieo-|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# Формат B — Open Questions
OQ_BLOCK_SPLIT_RE = re.compile(
    r'(?=(?:Open\s+)?(?:Question|Problem)\s+\d+[.\s])',
    re.IGNORECASE,
)
OQ_TITLE_RE = re.compile(
    r'(?:Open\s+)?(?:Question|Problem)\s+(\d+)[.\s]+[“«"\'`]?([^”»"\'`\n]{1,140})',
    re.IGNORECASE,
)
SOLUTION_BOUNDARY_RE = re.compile(
    r'^\s*(?:Solution|Marking\s+[Ss]cheme)\s*$',
    re.MULTILINE,
)
SUBPART_RE = re.compile(
    r'(?:\(([a-e])\)|([a-e])\))\s+\((\d+)\s*(?:rp|pr|points?|marks?)[^)]*\)',
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────────────────────

def md5(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def clean_text(text: str) -> str:
    """Убирает невидимые символы Unicode."""
    return INVISIBLE_RE.sub('', text)


def extract_text(pdf_path: Path) -> str:
    """Читает PDF и возвращает полный текст, очищенный от невидимых символов."""
    doc = fitz.open(str(pdf_path))
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return clean_text('\n'.join(pages))


def get_first_pages_text(pdf_path: Path, n: int = 3) -> str:
    """Возвращает текст первых N страниц, очищенный."""
    doc = fitz.open(str(pdf_path))
    pages = [doc[i].get_text() for i in range(min(n, len(doc)))]
    doc.close()
    return clean_text('\n'.join(pages))


def extract_year_track(text: str) -> tuple:
    """Извлекает год и трек из текста (первые 3 страницы)."""
    year_m = YEAR_RE.search(text)
    year = year_m.group(1) if year_m else 'Unknown'

    track_m = TRACK_RE.search(text)
    track = track_m.group(1).title() if track_m else 'Economics'
    # Нормализуем «Financial Literacy» (может быть с разным пробелом)
    track = re.sub(r'\s+', ' ', track).strip()

    return year, track


def _make_base_slug(name: str) -> str:
    """Простой ASCII-slug для тега."""
    s = name.lower()
    # Транслит простых символов
    trans = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
        'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
        'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
        'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    s = ''.join(trans.get(c, c) for c in s)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:110] or 'tag'


def ensure_tag(name: str, cache: dict) -> Tag:
    """Находит или создаёт Tag с указанным именем."""
    if name in cache:
        return cache[name]
    try:
        tag = Tag.objects.get(name=name)
        cache[name] = tag
        return tag
    except Tag.DoesNotExist:
        pass
    base_slug = _make_base_slug(name)
    slug = base_slug
    for attempt in range(1, 300):
        try:
            with transaction.atomic():
                tag = Tag.objects.create(name=name[:99], slug=slug[:119])
            cache[name] = tag
            return tag
        except IntegrityError:
            slug = f'{base_slug}-{attempt}'[:119]
    raise RuntimeError(f'Не удалось создать тег «{name}»')


# ──────────────────────────────────────────────────────────────────────────────
# Парсер формата A — MCQ
# ──────────────────────────────────────────────────────────────────────────────

def _parse_sf1_block(num, topic, body):
    """SF1: варианты «A. text», правильный — «Correct answer: X»."""
    # Находим начала вариантов A/B/C/D (строка начинается с «X. »)
    opt_starts = list(re.finditer(r'^([A-D])\.\s+', body, re.MULTILINE))
    if not opt_starts:
        return None

    q_text = body[:opt_starts[0].start()].strip()
    options = {}
    for i, m in enumerate(opt_starts):
        letter = m.group(1)
        start = m.end()
        end = opt_starts[i + 1].start() if i + 1 < len(opt_starts) else len(body)
        text = body[start:end]
        # Убираем «Correct answer» и всё после него из текста варианта
        ca = re.search(r'\nCorrect\s*answer', text, re.IGNORECASE)
        if ca:
            text = text[:ca.start()]
        options[letter] = text.strip()

    correct_m = MCQ_CORRECT_ANS_RE.search(body)
    correct = correct_m.group(1).upper() if correct_m else None

    expl_m = EXPLANATION_RE.search(body)
    explanation = expl_m.group(1).strip() if expl_m else ''

    return {
        'num': num, 'topic': topic,
        'q_text': q_text, 'options': options,
        'correct': correct, 'explanation': explanation,
    }


def _parse_sf2_block(num, topic, body):
    """SF2: таблица A/B/C/D (буква на отдельной строке), «Correct» — маркер."""
    lines = body.split('\n')
    q_lines = []
    options = {}
    correct_letter = None
    current = None
    opt_buf = []
    in_options = False

    for line in lines:
        s = line.strip()
        if s in ('A', 'B', 'C', 'D'):
            in_options = True
            if current is not None:
                options[current] = '\n'.join(opt_buf).strip()
            current = s
            opt_buf = []
        elif s == 'Correct' and current is not None:
            correct_letter = current
        elif re.match(r'^Explanation\s*[:\.\s]', s, re.IGNORECASE) and in_options:
            if current:
                options[current] = '\n'.join(opt_buf).strip()
                current = None
            break
        elif re.match(r'^(?:IEO|ecolymp|ieo-)', s, re.IGNORECASE) and in_options:
            if current:
                options[current] = '\n'.join(opt_buf).strip()
                current = None
            break
        elif not in_options:
            q_lines.append(line)
        else:
            opt_buf.append(line)

    if current is not None and current not in options:
        options[current] = '\n'.join(opt_buf).strip()

    q_text = '\n'.join(q_lines).strip()
    expl_m = EXPLANATION_RE.search(body)
    explanation = expl_m.group(1).strip() if expl_m else ''

    return {
        'num': num, 'topic': topic,
        'q_text': q_text, 'options': options,
        'correct': correct_letter, 'explanation': explanation,
    }


def parse_mcq_file(full_text: str) -> list:
    """Возвращает список MCQ-записей из Format A файла."""
    records = []
    for m in MCQ_BLOCK_RE.finditer(full_text):
        num, topic, body = m.group(1), m.group(2).strip(), m.group(3).strip()
        # Определяем sub-формат
        if MCQ_CORRECT_ANS_RE.search(body):
            rec = _parse_sf1_block(num, topic, body)
        else:
            rec = _parse_sf2_block(num, topic, body)
        if rec and rec.get('options'):
            records.append(rec)
    return records


# ──────────────────────────────────────────────────────────────────────────────
# Парсер формата B — Open Questions
# ──────────────────────────────────────────────────────────────────────────────

def parse_oq_file(full_text: str) -> list:
    """Возвращает список записей вопросов из Format B файла."""
    blocks = OQ_BLOCK_SPLIT_RE.split(full_text)
    questions = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        title_m = OQ_TITLE_RE.match(block)
        if not title_m:
            continue

        num = title_m.group(1)
        title = title_m.group(2).strip().rstrip('.,').strip()
        body = block[title_m.end():]

        # Убираем строку с баллами вида «(30 raw points)»
        body = re.sub(r'^\s*\(\d+\s*raw\s*points?\)\s*\n', '', body, flags=re.IGNORECASE)

        # Граница решения
        sol_m = SOLUTION_BOUNDARY_RE.search(body)
        if sol_m:
            statement = body[:sol_m.start()].strip()
            solution = body[sol_m.end():].strip()
        else:
            statement = body.strip()
            solution = ''

        if not statement:
            continue

        # Подпункты
        parts = []
        sp_matches = list(SUBPART_RE.finditer(statement))
        for i, sp_m in enumerate(sp_matches):
            letter = sp_m.group(1) or sp_m.group(2)  # (a) или a)
            points = int(sp_m.group(3))
            text_start = sp_m.end()
            text_end = sp_matches[i + 1].start() if i + 1 < len(sp_matches) else len(statement)
            part_text = statement[text_start:text_end].strip()
            parts.append({'label': letter, 'points': points, 'text': part_text})

        questions.append({
            'num': num,
            'title': title,
            'statement': statement,
            'solution': solution,
            'parts': parts,
        })

    return questions


# ──────────────────────────────────────────────────────────────────────────────
# Сохранение в базу
# ──────────────────────────────────────────────────────────────────────────────

def save_mcq_record(rec, source, note, tags, existing_hashes, dry_run):
    """Создаёт Problem + ProblemParts для MCQ-записи. Возвращает True при создании."""
    stmt = rec['q_text']
    if not stmt:
        stmt = rec['topic']
    stmt_hash = md5(stmt)
    if stmt_hash in existing_hashes:
        return False, 'skip'

    if dry_run:
        existing_hashes.add(stmt_hash)
        return True, 'dry'

    try:
        with transaction.atomic():
            title = f"MCQ {rec['num']}. {rec['topic']}"[:200]
            p = Problem.objects.create(
                title=title,
                statement=stmt,
                solution=rec.get('explanation', ''),
                difficulty=DIFFICULTY,
                status=Problem.Status.PUBLISHED,
                content_hash=stmt_hash,
                problem_type='тест: один ответ',
            )
            p.tags.add(*tags)

            SourceReference.objects.create(problem=p, source=source, note=note)

            correct = rec.get('correct')
            for order, letter in enumerate('ABCD'):
                opt_text = rec['options'].get(letter, '')
                if not opt_text and letter not in rec['options']:
                    continue
                answer = 'верно' if letter == correct else 'неверно'
                ProblemPart.objects.create(
                    problem=p,
                    label=letter,
                    statement=opt_text,
                    answer=answer,
                    order=order,
                )

        existing_hashes.add(stmt_hash)
        return True, 'ok'
    except Exception as exc:
        return False, str(exc)


def save_oq_record(rec, source, note, tags, existing_hashes, dry_run):
    """Создаёт Problem + ProblemParts для Open Question записи."""
    stmt = rec['statement']
    stmt_hash = md5(stmt)
    if stmt_hash in existing_hashes:
        return False, 'skip'

    if dry_run:
        existing_hashes.add(stmt_hash)
        return True, 'dry'

    try:
        with transaction.atomic():
            title = f"Open Question {rec['num']}: {rec['title']}"[:200]
            p = Problem.objects.create(
                title=title,
                statement=stmt,
                solution=rec.get('solution', ''),
                difficulty=DIFFICULTY,
                status=Problem.Status.PUBLISHED,
                content_hash=stmt_hash,
                problem_type='',
            )
            p.tags.add(*tags)

            SourceReference.objects.create(problem=p, source=source, note=note)

            for order, part in enumerate(rec.get('parts', [])):
                ProblemPart.objects.create(
                    problem=p,
                    label=part['label'],
                    statement=part['text'],
                    answer='',
                    points=part['points'],
                    order=order,
                )

        existing_hashes.add(stmt_hash)
        return True, 'ok'
    except Exception as exc:
        return False, str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# Команда
# ──────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импортирует задания IEO из PDF-файлов в папке materials/задания с прошлых IEO/'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Показать статистику без записи в базу',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if not IEO_FOLDER.exists():
            self.stderr.write(self.style.ERROR(f'Папка не найдена: {IEO_FOLDER}'))
            return

        pdf_files = sorted(IEO_FOLDER.glob('*.pdf'))
        if not pdf_files:
            self.stderr.write(self.style.ERROR('PDF-файлы не найдены'))
            return

        self.stdout.write(f'Найдено PDF файлов: {len(pdf_files)}')
        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')

        # ── Источник ─────────────────────────────────────────────────────────
        source, created_src = Source.objects.get_or_create(
            name=SOURCE_NAME,
            defaults={'kind': 'международная олимпиада'},
        )
        self.stdout.write(
            f'Источник «{source.name}» '
            f'{"создан" if created_src else "найден"}: #{source.pk}'
        )

        # ── Job ───────────────────────────────────────────────────────────────
        job = None
        if not dry_run:
            job = Job.objects.create(
                kind=Job.Kind.IMPORT,
                status=Job.Status.RUNNING,
                params={'folder': str(IEO_FOLDER), 'files': len(pdf_files)},
            )
            self.stdout.write(f'Job #{job.pk} создан')

        # ── Теги ─────────────────────────────────────────────────────────────
        tag_cache: dict = {t.name: t for t in Tag.objects.all()}
        tag_mcq = ensure_tag('MCQ', tag_cache)
        tag_oq = ensure_tag('Open Question', tag_cache)
        tag_ieo = ensure_tag('IEO', tag_cache)

        # ── Кэш хэшей ────────────────────────────────────────────────────────
        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='')
            .values_list('content_hash', flat=True)
        )

        # ── Счётчики ─────────────────────────────────────────────────────────
        files_done = mcq_created = oq_created = errors = skipped = 0
        total_records: list = []  # (rec, fmt, tags, note)

        # ── Сбор всех записей из файлов ───────────────────────────────────────
        self.stdout.write('\nАнализ файлов...')
        for pdf in pdf_files:
            try:
                first_text = get_first_pages_text(pdf, n=3)
                year, track = extract_year_track(first_text)
                note = f'{year}, {track}'
                is_mcq = bool(MCQ_DETECT_RE.search(first_text))

                full_text = extract_text(pdf)

                if is_mcq:
                    records = parse_mcq_file(full_text)
                    fmt = 'MCQ'
                    tags = [tag_mcq, tag_ieo]
                else:
                    records = parse_oq_file(full_text)
                    fmt = 'OQ'
                    tags = [tag_oq, tag_ieo]

                self.stdout.write(
                    f'  {pdf.name[:40]}  [{fmt}]  год={year}  трек={track}  '
                    f'задач={len(records)}'
                )
                for rec in records:
                    total_records.append((rec, fmt, tags, note))

            except Exception as exc:
                self.stderr.write(f'  Ошибка чтения {pdf.name}: {exc}')
                errors += 1

        self.stdout.write(f'\nВсего записей собрано: {len(total_records)}')

        # ── Основной цикл по батчам ───────────────────────────────────────────
        batch_num = 0
        for batch_start in range(0, len(total_records), BATCH_SIZE):
            batch = total_records[batch_start:batch_start + BATCH_SIZE]
            batch_num += 1

            for rec, fmt, tags, note in batch:
                if fmt == 'MCQ':
                    ok, reason = save_mcq_record(
                        rec, source, note, tags, existing_hashes, dry_run
                    )
                    if ok:
                        mcq_created += 1
                    elif reason == 'skip':
                        skipped += 1
                    else:
                        errors += 1
                        if reason not in ('skip', 'dry', 'ok'):
                            self.stderr.write(f'  Ошибка MCQ {rec.get("num")}: {reason}')
                else:
                    ok, reason = save_oq_record(
                        rec, source, note, tags, existing_hashes, dry_run
                    )
                    if ok:
                        oq_created += 1
                    elif reason == 'skip':
                        skipped += 1
                    else:
                        errors += 1
                        if reason not in ('skip', 'dry', 'ok'):
                            self.stderr.write(f'  Ошибка OQ {rec.get("num")}: {reason}')

            done = min(batch_start + BATCH_SIZE, len(total_records))
            progress = int(done / len(total_records) * 100) if total_records else 100

            if job:
                job.progress = progress
                job.result = {
                    'mcq_created': mcq_created,
                    'oq_created': oq_created,
                    'skipped': skipped,
                    'errors': errors,
                }
                job.save(update_fields=['progress', 'result'])

            self.stdout.write(
                f'  [{done:3d}/{len(total_records)}]  '
                f'MCQ: {mcq_created},  OQ: {oq_created},  '
                f'пропущено: {skipped},  ошибок: {errors}'
            )

        # ── Завершаем Job ─────────────────────────────────────────────────────
        if job:
            job.status = Job.Status.DONE
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = {
                'files_processed': len(pdf_files),
                'mcq_created': mcq_created,
                'oq_created': oq_created,
                'skipped': skipped,
                'errors': errors,
            }
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!\n'
            f'  Файлов обработано:    {len(pdf_files)}\n'
            f'  MCQ создано:          {mcq_created}\n'
            f'  Open Questions создано: {oq_created}\n'
            f'  Пропущено (дубли):    {skipped}\n'
            f'  Ошибок:               {errors}\n'
            + (f'  Job #{job.pk}: {job.status}' if job else '')
        ))
